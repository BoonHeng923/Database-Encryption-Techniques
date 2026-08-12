"""Regression check for the report's headline security contrast (plan B.12), run purely
in-memory (no live database needed -- `attack.py` only ever consumes token/volume/id
tuples, so an in-memory `{token: [records]}` index is a faithful stand-in for a real
adapter's `query_equality`).

Locks in, on the plan's vetted `lab_orders`/`specific_diagnostic_test` field at full
flattening (decoy_target_ratio=1.0, where the contrast is cleanest):

1. C's naive decoys are filterable: recovery rises once the realism filter is applied.
2. D's generative decoys survive the filter: filtered ~= unfiltered.
3. D reduces recovery well below B's (the headline B->D drop).

Run with: ./.venv/Scripts/python.exe -m pytest tests/
"""
from __future__ import annotations

from collections import defaultdict

from src.core import config, dataset, encryption, schema, workload
from src.core.attack import (
    ExecutedQuery,
    apply_realism_filter,
    build_realism_keep_map,
    run_count_attack,
)
from src.core.decoys import build_joint_distribution
from src.core.records import prepare_records

SCALE = 1000
RATIO = 1.0  # full flattening -- where the C-vs-D contrast is starkest


def _run_attack(df, approach: str):
    key = encryption.derive_token_key("lab_orders" if approach == "D" else None)
    records = prepare_records(df, approach, "lab_orders", config.SENSITIVE_FIELD, RATIO)

    by_token = defaultdict(list)
    for r in records:
        by_token[r.token].append(r)

    queries = workload.load_or_generate_workload(
        df, SCALE, sensitive_field=config.SENSITIVE_FIELD, n_queries=500, label="test_leakage_contrast"
    )
    value_counts = df[config.SENSITIVE_FIELD].astype(str).value_counts().to_dict()

    executed = []
    for value in queries:
        token = encryption.deterministic_token(value, key=key)
        hits = by_token.get(token, [])
        executed.append(ExecutedQuery(true_value=value, token=token, volume=len(hits), record_ids=[h.record_id for h in hits]))

    unfiltered = run_count_attack(approach, executed, value_counts).recovery_accuracy

    companion_fields = schema.COMPANION_FIELDS.get("lab_orders", [])
    joint_dist = build_joint_distribution(df, config.SENSITIVE_FIELD, companion_fields)
    keep_map = build_realism_keep_map(records, joint_dist, config.SENSITIVE_FIELD, companion_fields)
    filtered = run_count_attack(approach, apply_realism_filter(executed, keep_map), value_counts).recovery_accuracy

    return unfiltered, filtered


def test_headline_leakage_contrast():
    df, _ = dataset.load_scaled_dataset(SCALE)

    b_unfiltered, _ = _run_attack(df, "B")
    c_unfiltered, c_filtered = _run_attack(df, "C")
    d_unfiltered, d_filtered = _run_attack(df, "D")

    # 1. C's naive decoys get stripped by the realism filter, so filtered recovery is
    #    meaningfully higher than unfiltered (the attacker recovers more once decoys are
    #    identified and discarded).
    assert c_filtered > c_unfiltered + 0.10, (
        f"Approach C should be more filterable than this: unfiltered={c_unfiltered:.2%} filtered={c_filtered:.2%}"
    )

    # 2. D's generative decoys are individually realistic, so the filter can't tell them
    #    from real records: filtered stays close to unfiltered.
    assert abs(d_filtered - d_unfiltered) < 0.05, (
        f"Approach D's decoys should survive the realism filter: unfiltered={d_unfiltered:.2%} filtered={d_filtered:.2%}"
    )

    # 3. The headline result: D reduces recovery well below B's, even under the filter.
    assert d_filtered < b_unfiltered - 0.20, (
        f"Approach D should meaningfully reduce recovery vs. B: B={b_unfiltered:.2%} D(filtered)={d_filtered:.2%}"
    )
