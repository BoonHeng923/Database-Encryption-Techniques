"""Decoy record generation and the attacker-side realism filter (plan B.4.2 / B.9).

Two generators share the same *targeting* policy (`compute_target_counts`) so C and D
differ only in *realism*, isolating exactly the thing the report needs to show:

- `naive_decoy_generator` (Approach C): each companion field is sampled independently
  from its own marginal distribution, ignoring real-world field co-occurrence. This is
  cheap but produces field combinations that rarely or never occur in the real data --
  exactly what `realism_filter` below is built to detect.
- `conditional_decoy_generator` (Approach D): companion fields are sampled jointly from
  the empirical distribution conditioned on the target value, i.e. a real co-occurring
  combination is reused verbatim. This is a lightweight conditional sampler, not a full
  CTGAN/GAN -- an explicitly permitted simplification (plan B.4.2/B.9) that still gives
  every decoy record a real joint probability, so it survives the realism filter.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
import pandas as pd

from src.core import config


def compute_target_counts(value_counts: dict[str, int], target_ratio: float = config.DECOY_TARGET_RATIO) -> dict[str, int]:
    """How many decoys each value needs so its *observed* count rises toward
    `target_ratio` x the most frequent value's count -- flattening the frequency signal
    the count attack exploits. Shared by both C and D so targeting is identical and only
    per-record realism differs (B.4.2/B.9)."""
    if not value_counts:
        return {}
    target = max(value_counts.values()) * target_ratio
    return {value: max(0, round(target - count)) for value, count in value_counts.items()}


def build_joint_distribution(df: pd.DataFrame, field: str, companion_fields: list[str]) -> dict[tuple, float]:
    """Empirical joint probability of (field, *companion_fields) combinations in the real
    data -- the attacker's realism-check reference distribution."""
    cols = [field] + list(companion_fields)
    counts = df[cols].astype(str).value_counts()
    total = int(counts.sum())
    dist: dict[tuple, float] = {}
    for idx, c in counts.items():
        key = idx if isinstance(idx, tuple) else (idx,)
        dist[key] = c / total
    return dist


def naive_decoy_generator(
    df: pd.DataFrame, field: str, companion_fields: list[str], seed: int | None = None
) -> Callable[[str, int], list[dict]]:
    rng = np.random.default_rng(seed)
    marginals = {}
    for c in companion_fields:
        vc = df[c].astype(str).value_counts(normalize=True)
        marginals[c] = (vc.index.to_numpy(), vc.to_numpy())

    def sample(value: str, n: int) -> list[dict]:
        rows = []
        for _ in range(n):
            row = {field: value}
            for c, (values, probs) in marginals.items():
                row[c] = rng.choice(values, p=probs)
            rows.append(row)
        return rows

    return sample


def conditional_decoy_generator(
    df: pd.DataFrame, field: str, companion_fields: list[str], seed: int | None = None
) -> Callable[[str, int], list[dict]]:
    rng = np.random.default_rng(seed)
    groups = {
        value: g[companion_fields].astype(str).reset_index(drop=True)
        for value, g in df.groupby(field)
    }
    overall = df[companion_fields].astype(str).reset_index(drop=True)

    def sample(value: str, n: int) -> list[dict]:
        pool = groups.get(value)
        if pool is None or len(pool) == 0:
            pool = overall
        idx = rng.integers(0, len(pool), size=n)
        rows = []
        for i in idx:
            row = {field: value}
            row.update(pool.iloc[int(i)].to_dict())
            rows.append(row)
        return rows

    return sample


def realism_filter(
    records: Iterable[dict],
    joint_distribution: dict[tuple, float],
    field: str,
    companion_fields: list[str],
    threshold: float,
) -> list[bool]:
    """Attacker-side filter (used by the value-recovery attack for C/D, plan B.7 point 1):
    flags field-combinations with near-zero empirical joint probability as likely-decoy.
    Returns a keep_mask: True = looks realistic (kept as a candidate real record)."""
    cols = [field] + list(companion_fields)
    keep_mask = []
    for r in records:
        key = tuple(str(r.get(c, "")) for c in cols)
        prob = joint_distribution.get(key, 0.0)
        keep_mask.append(prob >= threshold)
    return keep_mask
