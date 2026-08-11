"""Dataset loading and scaling.

Primary source: "Adult inpatient patient portal data" (`data/raw/adult_inpatient_
patient_portal_data.xlsx`), 826,843 de-identified inpatient diagnostic-test records.
The sensitive/attack-target field is `specific_diagnostic_test` (297 distinct test
names, heavily skewed — see `src/analysis/dataset_profile.py` for the full B.5.1
sanity-check justifying this choice over the other categorical fields in the file).

A synthetic fallback with the same normalized schema is used only if the raw file is
missing, so the pipeline is still runnable end to end without it. Every run records
which source was used (`dataset_source` in the results) so report figures can be
clearly labelled.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core import config

# Raw Excel column name -> normalized snake_case column name.
_COLUMN_MAP = {
    "Unique De-Identified\nPatient Code #": "patient_code",
    "# of Admissions\nin 2018": "admissions_2018",
    "Initial Admission in 2018\nor Additional/Repeat": "admission_type",
    "Specific Diagnostic Test": "specific_diagnostic_test",
    "Diagnostic Test\nCategory": "diagnostic_test_category",
    "Sex": "sex",
    "Patient Portal\nStatus": "patient_portal_status",
    "Result Viewed\nin MyChart?": "result_viewed",
    "Most Common\nRace Categories": "race_category",
    "Race Category\nWhite vs. Non-White": "race_white_nonwhite",
    "Age at Time of Testing": "age_at_testing",
    "Age Category": "age_category",
    "Primary/Preferred Language": "preferred_language",
    "Primary/Preferred Language - English vs. Non-English": "language_en_nonen",
    "Proxy Access": "proxy_access",
    "Insurance category": "insurance_category",
}

COLUMNS = ["record_id"] + list(_COLUMN_MAP.values())

_RAW_CACHE_CSV = os.path.join(config.DATA_PROCESSED_DIR, "dataset_cache.csv")

# --- Synthetic fallback (only used if the real Excel file isn't present) ---
_SYNTHETIC_TESTS = [
    "BASIC METABOLIC PANEL", "MAGNESIUM", "CBC", "PHOSPHORUS", "PT/INR",
    "PTT", "LACTIC ACID", "ARTERIAL BLOOD GAS", "CHEST X-RAY", "POTASSIUM",
]
_SYNTHETIC_WEIGHTS = np.array([1 / (i + 1) for i in range(len(_SYNTHETIC_TESTS))])
_SYNTHETIC_WEIGHTS = _SYNTHETIC_WEIGHTS / _SYNTHETIC_WEIGHTS.sum()


@dataclass
class DatasetInfo:
    source: str  # "excel" or "synthetic"
    n_records: int
    sensitive_field: str
    value_counts: dict


def _read_excel_cached() -> pd.DataFrame:
    if os.path.exists(_RAW_CACHE_CSV):
        return pd.read_csv(_RAW_CACHE_CSV, dtype={"patient_code": str})

    df = pd.read_excel(config.RAW_EXCEL_PATH)
    df = df.rename(columns=_COLUMN_MAP)
    missing = set(_COLUMN_MAP.values()) - set(df.columns)
    if missing:
        raise ValueError(
            f"{config.RAW_EXCEL_PATH} is missing expected columns: {sorted(missing)}. "
            "Confirm this is the 'Adult inpatient patient portal data' export."
        )
    df[config.SENSITIVE_FIELD] = df[config.SENSITIVE_FIELD].astype(str).str.strip()
    df = df.reset_index(drop=True)
    df.insert(0, "record_id", [f"raw-{i}" for i in range(len(df))])

    os.makedirs(config.DATA_PROCESSED_DIR, exist_ok=True)
    df.to_csv(_RAW_CACHE_CSV, index=False)
    return df


def _generate_synthetic_base(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(config.WORKLOAD_SEED)
    tests = rng.choice(_SYNTHETIC_TESTS, size=n, p=_SYNTHETIC_WEIGHTS)
    df = pd.DataFrame(
        {
            "record_id": [f"syn-{i}" for i in range(n)],
            "patient_code": rng.integers(0, n // 5 + 1, size=n).astype(str),
            "admissions_2018": rng.choice(["1", "More than 1"], size=n),
            "admission_type": rng.choice(["Initial", "Repeat"], size=n),
            "specific_diagnostic_test": tests,
            "diagnostic_test_category": "Chemistry",
            "sex": rng.choice(["M", "F"], size=n),
            "patient_portal_status": rng.choice(["Activated", "Inactive"], size=n),
            "result_viewed": rng.choice(["Viewed", "Not viewed"], size=n),
            "race_category": rng.choice(["White", "African American/Black", "Other"], size=n),
            "race_white_nonwhite": rng.choice(["White", "Non-White"], size=n),
            "age_at_testing": rng.integers(18, 95, size=n),
            "age_category": rng.choice(["18-25 years", "51-60 years", "61-70 years"], size=n),
            "preferred_language": "English",
            "language_en_nonen": "English",
            "proxy_access": rng.choice(["Yes", "No"], size=n),
            "insurance_category": rng.choice(["Commercial", "Public/Uninsured"], size=n),
        }
    )
    return df[COLUMNS]


def _load_raw() -> tuple[pd.DataFrame, str]:
    if os.path.exists(config.RAW_EXCEL_PATH):
        return _read_excel_cached(), "excel"
    return _generate_synthetic_base(n=20_000), "synthetic"


def full_dataset_size() -> int:
    return len(_load_raw()[0])


def load_scaled_dataset(n_records: int, sensitive_field: str = config.SENSITIVE_FIELD) -> tuple[pd.DataFrame, DatasetInfo]:
    """Return a dataframe of `n_records` rows, sub-sampled without replacement (plan
    B.5) from the full dataset with a fixed seed, or the full dataset unchanged if
    `n_records` >= its size (the top scale point)."""
    base, source = _load_raw()

    if n_records >= len(base):
        scaled = base.copy()
    else:
        seed = int(hashlib.sha256(f"{config.WORKLOAD_SEED}-{n_records}".encode()).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(base), size=n_records, replace=False)
        scaled = base.iloc[idx].reset_index(drop=True).copy()

    scaled["record_id"] = [f"{source}-{n_records}-{i}" for i in range(len(scaled))]

    value_counts = scaled[sensitive_field].value_counts().to_dict()
    info = DatasetInfo(
        source=source,
        n_records=len(scaled),
        sensitive_field=sensitive_field,
        value_counts=value_counts,
    )
    return scaled, info
