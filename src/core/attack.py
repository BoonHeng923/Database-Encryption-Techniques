"""Documented access-pattern / volume leakage-abuse attack (plan section B.7).

This is a classic *count attack* (Kellaris et al., "Generic Attacks on Secure Outsourced
Databases", ACM CCS 2016; see also Sap/IHOP-style frequency-matching attacks) [X4]:

The adversary is honest-but-curious: it observes, for every query, only (a) which
encrypted token was queried (search pattern — repeats are visible because the token is
deterministic) and (b) how many records were returned (volume). It also has auxiliary
knowledge of the sensitive field's true population frequency distribution (e.g. from a
public census/statistics source, or — as modelled here — the dataset's own marginal
distribution, which is the standard assumption in this line of attacks). It matches
observed (token, volume) pairs to the plaintext value whose true frequency is closest,
via an optimal (minimum absolute-error) assignment.

This exact code runs unmodified against every engine — the attack only consumes
(token, volume) pairs, never anything engine-specific, which is what makes it a fair,
common benchmark across SQL and NoSQL (plan section B.1/B.7).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class ExecutedQuery:
    true_value: str
    token: bytes | None  # None for Approach A, where the query is plaintext already
    volume: int


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

    tokens = list(by_token.keys())
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
