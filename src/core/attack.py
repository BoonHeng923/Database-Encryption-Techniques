"""Documented access-pattern / volume / linkage leakage-abuse attacks (plan section B.7).

**1. Value recovery** (`run_count_attack`) is a classic *count attack* (Kellaris et al.,
"Generic Attacks on Secure Outsourced Databases", ACM CCS 2016; see also Sap/IHOP-style
frequency-matching attacks) [X4]: the adversary observes, for every query, only (a) which
encrypted token was queried (search pattern) and (b) how many records were returned
(volume), plus auxiliary knowledge of the sensitive field's true population frequency
distribution, and matches observed (token, volume) pairs to the plaintext value whose
true frequency is closest via an optimal (minimum absolute-error) assignment. For
Approaches C/D the attacker is additionally allowed a **realism filter** (plan B.7 point
1, threat model B.2): it may discard returned records whose companion-field combination
looks statistically implausible before counting volume. `apply_realism_filter` produces
the filtered view; callers run `run_count_attack` once unfiltered and once filtered to
report both, per plan B.8.

**2. Linkage recovery** (`run_linkage_attack`) targets the cross-collection `patient_code`
link (plan B.7 point 2): the attacker groups records across `patients`/`lab_orders`/
`billing` by matching `patient_token` bytes and scores the fraction of true patient-level
links it recovers. B/C use one shared token key across collections, so this is ~100%; D
uses a distinct key per collection, so token equality stops being a valid link signal and
recovery collapses.

This code runs unmodified against every engine -- it only ever consumes (token, volume,
record_ids) tuples and the client-side ground truth kept for scoring, never anything
engine-specific, which is what makes it a fair, common benchmark across NoSQL engines
(plan section B.1/B.7).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.core import decoys


@dataclass
class ExecutedQuery:
    true_value: str
    token: bytes | None  # None for Approach A, where the query is plaintext already
    volume: int
    record_ids: list = field(default_factory=list)  # ids returned, for the realism filter


@dataclass
class AttackResult:
    approach: str
    n_queries: int
    n_correct: int
    recovery_accuracy: float
    n_unique_tokens: int


def run_count_attack(
    approach: str,
    executed: list[ExecutedQuery],
    true_value_counts: dict[str, int],
) -> AttackResult:
    n = len(executed)

    if approach == "A":
        # The query itself is plaintext on the wire/in the query log: recovery is
        # trivial by definition. Included as the sanity-check control (B.7 step 4).
        return AttackResult(approach="A", n_queries=n, n_correct=n, recovery_accuracy=1.0, n_unique_tokens=n)

    # 1. What the server/attacker actually observes: token -> (a representative
    #    volume, the set of query occurrences that used it).
    by_token: dict[bytes, list[ExecutedQuery]] = {}
    for q in executed:
        by_token.setdefault(q.token, []).append(q)

    # Shuffle token order before matching (fixed seed, so it's reproducible but decoupled
    # from *this* run's dict-insertion order). Insertion order tracks the order queries
    # were first seen, which -- since the workload samples proportional to true frequency
    # -- silently correlates with the true-frequency-descending candidate order below. When
    # decoys flatten observed volumes to an exact tie (full flattening: every candidate's
    # observed count is identical), `linear_sum_assignment` still resolves the tie
    # deterministically by row/column index, so without this shuffle the attacker would
    # "recover" values via that ordering coincidence rather than any real signal in the
    # data -- i.e. Approach D could look like it's failing to reduce recovery purely
    # because of how Python dicts preserve insertion order, not because of any leakage.
    tokens = list(by_token.keys())
    np.random.default_rng(0).shuffle(tokens)
    observed_volumes = [by_token[t][0].volume for t in tokens]

    # 2. Auxiliary knowledge: true frequency of each candidate plaintext value.
    #    Restrict to the top-k candidates (k = number of distinct tokens observed) by
    #    true frequency, the standard reduction when the attacker doesn't know in
    #    advance which values were queried at all.
    candidates = sorted(true_value_counts.items(), key=lambda kv: kv[1], reverse=True)[: len(tokens)]
    candidate_values = [c[0] for c in candidates]
    candidate_counts = [c[1] for c in candidates]

    # 3. Optimal assignment minimizing total |observed - candidate| error.
    cost = np.abs(np.subtract.outer(observed_volumes, candidate_counts)).astype(float)
    row_idx, col_idx = linear_sum_assignment(cost)
    token_to_guess = {tokens[r]: candidate_values[c] for r, c in zip(row_idx, col_idx)}

    # 4. Score every individual query occurrence against its guessed value.
    n_correct = sum(1 for q in executed if token_to_guess.get(q.token) == q.true_value)

    return AttackResult(
        approach=approach,
        n_queries=n,
        n_correct=n_correct,
        recovery_accuracy=n_correct / n if n else 0.0,
        n_unique_tokens=len(tokens),
    )


def apply_realism_filter(
    executed: list[ExecutedQuery],
    realism_keep: dict[str, bool],
) -> list[ExecutedQuery]:
    """Rebuilds `executed` with `volume` replaced by the count of returned record_ids that
    survive the realism filter (plan B.7 point 1). `realism_keep` maps record_id -> True
    if that record's companion-field combination looks realistic (see
    `build_realism_keep_map` below); ids absent from the map are kept by default."""
    filtered = []
    for q in executed:
        kept = sum(1 for rid in q.record_ids if realism_keep.get(rid, True))
        filtered.append(ExecutedQuery(true_value=q.true_value, token=q.token, volume=kept, record_ids=q.record_ids))
    return filtered


def build_realism_keep_map(
    stored_records: list,
    joint_distribution: dict[tuple, float],
    sensitive_field_name: str,
    companion_fields: list[str],
    threshold: float = 1e-6,
) -> dict[str, bool]:
    """Builds the record_id -> keep_bool map `apply_realism_filter` needs, by running
    `decoys.realism_filter` over every stored record's ground-truth field values (real
    records always pass; naive decoys mostly fail; generative decoys mostly pass -- this
    is the C-vs-D gap the attack is meant to expose)."""
    rows = []
    for r in stored_records:
        row = {sensitive_field_name: r.plain_value}
        row.update(r.companion_values or {})
        rows.append(row)
    keep_mask = decoys.realism_filter(rows, joint_distribution, sensitive_field_name, companion_fields, threshold)
    return {r.record_id: keep for r, keep in zip(stored_records, keep_mask)}


@dataclass
class LinkageAttackResult:
    approach: str
    collection_pairs: dict
    linkage_recovery_accuracy: float


def run_linkage_attack(approach: str, collections_records: dict[str, list]) -> LinkageAttackResult:
    """Cross-collection linkage attack (plan B.7 point 2): for each pair of collections,
    group real records by patient_code and check whether the token (or, for plaintext
    Approach A, the value itself) used for that patient matches across the pair -- the
    attacker's only linkage signal is token equality, since it never sees plaintext for
    B/C/D."""
    names = sorted(collections_records.keys())
    per_pair: dict[tuple, float] = {}

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]

            def link_signal(records):
                out = {}
                for r in records:
                    if r.is_dummy or r.plain_patient_code is None:
                        continue
                    out[r.plain_patient_code] = r.patient_token if r.patient_token is not None else r.plain_patient_code
                return out

            signal_a = link_signal(collections_records[a])
            signal_b = link_signal(collections_records[b])
            shared = set(signal_a) & set(signal_b)
            if not shared:
                continue
            n_correct = sum(1 for p in shared if signal_a[p] == signal_b[p])
            per_pair[(a, b)] = n_correct / len(shared)

    overall = sum(per_pair.values()) / len(per_pair) if per_pair else (1.0 if approach == "A" else 0.0)
    return LinkageAttackResult(approach=approach, collection_pairs=per_pair, linkage_recovery_accuracy=overall)
