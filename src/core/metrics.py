"""Result-row schema and latency summary helpers (feeds plan section B.8 / Results)."""
from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass

import numpy as np

from src.core import config

RESULTS_CSV = os.path.join(config.RESULTS_DIR, "raw_results.csv")

FIELDNAMES = [
    "dataset_source",
    "scale",
    "engine",
    "approach",
    "repeat",
    "n_queries",
    "mean_latency_ms",
    "p95_latency_ms",
    "throughput_qps",
    "cpu_percent",
    "storage_mb",
    "ciphertext_expansion_factor",
    "recovery_accuracy",
    "n_unique_tokens",
]


@dataclass
class ResultRow:
    dataset_source: str
    scale: int
    engine: str
    approach: str
    repeat: int
    n_queries: int
    mean_latency_ms: float
    p95_latency_ms: float
    throughput_qps: float
    cpu_percent: float
    storage_mb: float
    ciphertext_expansion_factor: float
    recovery_accuracy: float
    n_unique_tokens: int


def latency_summary(latencies_ms: list[float]) -> tuple[float, float]:
    arr = np.array(latencies_ms)
    return float(arr.mean()), float(np.percentile(arr, 95))


def append_result(row: ResultRow) -> None:
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    write_header = not os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(asdict(row))
