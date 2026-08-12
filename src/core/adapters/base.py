"""Shared storage-adapter interface (plan section B.3 / B.9).

Everything above this line (encryption, schema, decoys, secret_id, workload, attack,
metrics) is engine-agnostic. Everything below it is a thin per-engine adapter
implementing this same interface, so adding a fourth engine later only means writing one
new class here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class QueryResult:
    latency_ms: float
    volume: int  # number of rows/documents returned to the "server-observing" attacker
    record_ids: list = field(default_factory=list)  # ids returned, for access-pattern bookkeeping


class StorageAdapter(ABC):
    """One adapter instance is bound to a single engine and reused across approaches and
    collections. Every storage unit is addressed as `{approach}_{collection}`."""

    engine_name: str

    @abstractmethod
    def setup(self, approach: str, collection: str) -> None:
        """(Re)create a clean table/collection for `(approach, collection)`."""

    @abstractmethod
    def bulk_load(
        self, approach: str, collection: str, df, sensitive_field: str, decoy_target_ratio: float | None = None
    ) -> None:
        """Load the dataframe into storage for `(approach, collection)`, applying that
        approach's transform (plaintext / deterministic token / token + decoys) via
        `src.core.records.prepare_records`. `decoy_target_ratio` is forwarded to
        `prepare_records` for C/D (ignored otherwise) -- see config.DECOY_TARGET_RATIOS."""

    @abstractmethod
    def query_equality(
        self, approach: str, collection: str, value: str, token: bytes | None = None
    ) -> QueryResult:
        """Execute one equality query and return what an observing server/attacker would
        see: latency, volume, and the returned ids. For approach 'A' the query is
        plaintext `value`; for 'B'/'C'/'D' the caller supplies the precomputed
        deterministic `token` (client-side encryption happens once in the experiment
        runner, not per-adapter, so every engine queries the exact same ciphertext)."""

    @abstractmethod
    def storage_size_mb(self, approach: str, collection: str) -> float:
        """Total on-disk size (data + index) for the approach/collection's table."""

    @abstractmethod
    def close(self) -> None:
        ...
