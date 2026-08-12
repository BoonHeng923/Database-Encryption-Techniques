"""Builds the three linked collections from the flat dataset (plan B.5).

`patients`   -- one row per patient: patient_code, race_category, age_category.
`lab_orders` -- one row per test event: patient_code, specific_diagnostic_test,
                diagnostic_test_category. Single-collection mode uses this collection
                alone (it carries the plan's sensitive/attack field).
`billing`    -- one row per test event: patient_code, a derived cost field/category.

All three carry `patient_code`, the field the cross-collection linkage attack targets.
Each collection also gets its own queryable "sensitive field" so the value-recovery
attack has something to target in multi-collection mode too.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.core import config

QUERY_FIELD = {
    "patients": "race_category",
    "lab_orders": config.SENSITIVE_FIELD,
    "billing": "cost_category",
}

# Companion (non-queried, non-link) fields used by the decoy generators (B.4.2) to
# preserve realistic co-occurrence per collection.
COMPANION_FIELDS = {
    "patients": ["age_category"],
    "lab_orders": ["diagnostic_test_category"],
    "billing": ["diagnostic_test_category"],
}


def _test_base_cost(test_name: str) -> float:
    digest = hashlib.sha256(test_name.encode()).hexdigest()
    return 50 + (int(digest[:8], 16) % 950)


def build_patients(df: pd.DataFrame) -> pd.DataFrame:
    patients = (
        df.sort_values("record_id")
        .drop_duplicates(subset=[config.LINK_FIELD], keep="first")[[config.LINK_FIELD, "race_category", "age_category"]]
        .reset_index(drop=True)
    )
    patients.insert(0, "record_id", [f"patients-{i}" for i in range(len(patients))])
    return patients


def build_lab_orders(df: pd.DataFrame) -> pd.DataFrame:
    lab_orders = df[[config.LINK_FIELD, config.SENSITIVE_FIELD, "diagnostic_test_category"]].reset_index(drop=True).copy()
    lab_orders.insert(0, "record_id", [f"lab_orders-{i}" for i in range(len(lab_orders))])
    return lab_orders


_COST_TIER_BINS = [-np.inf, 150, 400, 800, np.inf]
_COST_TIER_LABELS = ["tier_low", "tier_mid", "tier_high", "tier_premium"]


def build_billing(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(config.WORKLOAD_SEED)
    base_cost = df[config.SENSITIVE_FIELD].map(_test_base_cost).to_numpy()
    jitter = rng.normal(loc=1.0, scale=0.08, size=len(df))
    cost = np.round(base_cost * jitter, 2)
    # Fixed-threshold tiers, not pd.qcut: quantile bins are equal-count *by definition*
    # (each tier gets exactly len(df)/4 rows regardless of the underlying cost skew), which
    # silently erases the real skew this field has (cost is driven by test frequency, since
    # `_test_base_cost` is per test name and common tests repeat across many rows) and left
    # decoys with nothing to flatten -- cost_category came out perfectly uniform (250/250/
    # 250/250 at scale 1000), so B/C/D value-recovery on it was structurally identical.
    # Fixed dollar thresholds instead let the real per-test-frequency skew show through.
    cost_category = pd.cut(cost, bins=_COST_TIER_BINS, labels=_COST_TIER_LABELS)

    billing = pd.DataFrame(
        {
            config.LINK_FIELD: df[config.LINK_FIELD].to_numpy(),
            "diagnostic_test_category": df["diagnostic_test_category"].to_numpy(),
            "cost": cost,
            "cost_category": cost_category.astype(str),
        }
    )
    billing.insert(0, "record_id", [f"billing-{i}" for i in range(len(billing))])
    return billing


def build_collections(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "patients": build_patients(df),
        "lab_orders": build_lab_orders(df),
        "billing": build_billing(df),
    }
