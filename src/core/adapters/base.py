"""Shared storage-adapter interface (plan section B.3 / B.9).

Everything above this line (encryption, workload, attack, metrics) is engine-agnostic.
Everything below it is a thin per-engine adapter implementing this same interface, so
adding a seventh engine later only means writing one new class here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class QueryResult:
    latency_ms: float
    volume: int  # number of rows/documents returned to the "server-observing" attacker
    record_ids: list  # ids returned, for access-pattern bookkeeping


class StorageAdapter(ABC):
    """One adapter instance is bound to a single (engine) and reused across approaches."""

    engine_name: str

    @abstractmethod
    def setup(self, approach: str) -> None:
        """(Re)create a clean table/collection for `approach` ('A', 'B', or 'C')."""

    @abstractmethod
    def bulk_load(self, approach: str, df, sensitive_field: str) -> None:
        """Load the dataframe into storage for `approach`, applying that approach's
        transform to `sensitive_field` (plaintext / deterministic token / padded
        deterministic token)."""

    @abstractmethod
    def query_equality(self, approach: str, value: str, token: bytes | None = None) -> QueryResult:
        """Execute one equality query and return what an observing server/attacker
        would see: latency and volume. For approach 'A' the query is plaintext
        `value`; for 'B'/'C' the caller supplies the precomputed deterministic
        `token` (client-side encryption happens once in the experiment runner, not
        per-adapter, so every engine queries the exact same ciphertext)."""

    @abstractmethod
    def storage_size_mb(self, approach: str) -> float:
        """Total on-disk size (data + index) for the approach's table/collection."""

    @abstractmethod
    def close(self) -> None:
        ...
