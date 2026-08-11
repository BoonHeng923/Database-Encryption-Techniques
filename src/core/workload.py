"""Seeded query workload generator (plan section B.6).

Query targets are sampled *proportional to the sensitive field's own empirical
frequency* in the loaded dataset. Because that frequency is itself the auxiliary
knowledge the attacker in `attack.py` is assumed to know, this is exactly the skewed,
realistic access pattern that count-attacks are built to exploit — no separate Zipf
model is needed, the skew comes from the data itself.

The same frozen sequence of query target values is replayed against every approach
(A/B/C) and every engine at a given scale point, so approach/engine is the only thing
that varies between runs — required by the controlled-comparison design (B.2).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from src.core import config


def generate_workload(
    df: pd.DataFrame,
    scale: int,
    sensitive_field: str = config.SENSITIVE_FIELD,
    n_queries: int = config.DEFAULT_N_QUERIES,
) -> list[str]:
    seed = (config.WORKLOAD_SEED * 1_000_003 + scale) % (2**32)
    rng = np.random.default_rng(seed)

    values = df[sensitive_field].astype(str)
    counts = values.value_counts()
    population = counts.index.to_numpy()
    weights = counts.to_numpy() / counts.sum()

    queries = rng.choice(population, size=n_queries, p=weights).tolist()
    return queries


def workload_path(scale: int) -> str:
    return os.path.join(config.DATA_PROCESSED_DIR, f"workload_scale{scale}.json")


def save_workload(queries: list[str], scale: int) -> str:
    os.makedirs(config.DATA_PROCESSED_DIR, exist_ok=True)
    path = workload_path(scale)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queries, f)
    return path


def load_or_generate_workload(
    df: pd.DataFrame,
    scale: int,
    sensitive_field: str = config.SENSITIVE_FIELD,
    n_queries: int = config.DEFAULT_N_QUERIES,
) -> list[str]:
    path = workload_path(scale)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    queries = generate_workload(df, scale, sensitive_field, n_queries)
    save_workload(queries, scale)
    return queries
