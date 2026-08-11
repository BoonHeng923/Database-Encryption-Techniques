"""Turns a raw dataframe into the exact rows each approach stores, independent of the
storage engine. Both adapters call `prepare_records()` so the transform (and therefore
the leakage it produces or hides) is identical on Postgres and MongoDB.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from src.core import config, encryption


@dataclass
class StoredRecord:
    record_id: str
    is_dummy: bool
    token: bytes | None  # None for Approach A (plaintext, no token needed)
    plain_value: str | None  # only set for Approach A
    payload: bytes | None  # AES-GCM ciphertext of the non-queried fields; None for dummies


def _payload_fields(row: pd.Series, sensitive_field: str) -> dict:
    return {k: v for k, v in row.items() if k != sensitive_field}


def prepare_records(
    df: pd.DataFrame,
    approach: str,
    sensitive_field: str = config.SENSITIVE_FIELD,
    pad_bucket_size: int = config.PAD_BUCKET_SIZE,
) -> list[StoredRecord]:
    if approach == "A":
        return [
            StoredRecord(
                record_id=row["record_id"],
                is_dummy=False,
                token=None,
                plain_value=str(row[sensitive_field]),
                payload=None,
            )
            for _, row in df.iterrows()
        ]

    records: list[StoredRecord] = []
    groups: dict[bytes, list[tuple[str, bytes]]] = defaultdict(list)

    for _, row in df.iterrows():
        value = str(row[sensitive_field])
        token = encryption.deterministic_token(value)
        payload = encryption.encrypt_payload(_payload_fields(row, sensitive_field))
        records.append(
            StoredRecord(
                record_id=row["record_id"],
                is_dummy=False,
                token=token,
                plain_value=None,
                payload=payload,
            )
        )
        groups[token].append(row["record_id"])

    if approach == "C":
        # Volume-hiding: pad every token's group up to the next multiple of the bucket
        # size with dummy rows sharing the same token, so the *observed* result count
        # for a query no longer reveals the true frequency of that value.
        for token, ids in groups.items():
            target = math.ceil(len(ids) / pad_bucket_size) * pad_bucket_size
            n_dummies = target - len(ids)
            for i in range(n_dummies):
                records.append(
                    StoredRecord(
                        record_id=f"dummy-{token.hex()}-{i}",
                        is_dummy=True,
                        token=token,
                        plain_value=None,
                        payload=None,
                    )
                )
    elif approach != "B":
        raise ValueError(f"Unknown approach: {approach}")

    return records
