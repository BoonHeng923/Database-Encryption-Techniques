"""Turns a raw dataframe into the exact rows each approach stores, independent of the
storage engine. Every adapter calls `prepare_records()` so the transform (and therefore
the leakage it produces or hides) is a property of the pipeline, not of the engine.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from src.core import config, decoys, encryption, schema, secret_id


@dataclass
class StoredRecord:
    record_id: str  # server-visible id: the plain dataframe id (A/B) or the secret id(i) hex (C/D)
    is_dummy: bool  # ground truth only, for our own evaluation -- never persisted server-side
    token: bytes | None  # sensitive-field token; None for Approach A
    patient_token: bytes | None  # patient_code token, used by the linkage attack; None for A
    plain_value: str | None  # ground truth for scoring only, never persisted server-side
    plain_patient_code: str | None  # ground truth for scoring only, never persisted server-side
    payload: bytes | None  # AES-GCM ciphertext of the non-queried fields; None for A
    companion_values: dict | None = None  # ground truth for the realism-filter attack only


def _payload_fields(row: pd.Series, exclude: set[str]) -> dict:
    return {k: v for k, v in row.items() if k not in exclude}


def prepare_records(
    df: pd.DataFrame,
    approach: str,
    collection: str,
    sensitive_field: str | None = None,
    decoy_target_ratio: float | None = None,
) -> list[StoredRecord]:
    sensitive_field = sensitive_field or schema.QUERY_FIELD.get(collection, config.SENSITIVE_FIELD)
    link_field = config.LINK_FIELD
    has_link = link_field in df.columns

    if approach == "A":
        return [
            StoredRecord(
                record_id=row["record_id"],
                is_dummy=False,
                token=None,
                patient_token=None,
                plain_value=str(row[sensitive_field]),
                plain_patient_code=str(row[link_field]) if has_link else None,
                payload=None,
            )
            for _, row in df.iterrows()
        ]

    # NOTE: `plain_patient_code` is populated for every approach below, not just A. It is
    # never persisted server-side (adapters only ever touch record_id/token/patient_token
    # /payload) -- it exists purely so the simulated attacker's *scoring* code (attack.py)
    # can check ground truth, exactly like `ExecutedQuery.true_value` already does for the
    # value-recovery attack.

    if approach not in ("B", "C", "D"):
        raise ValueError(f"Unknown approach: {approach}")

    # B/C use the single global key (shared across every collection) for both the
    # sensitive field and patient_code -- this is *why* B/C leak cross-collection
    # linkage. D uses a distinct key per collection for both, breaking that linkage.
    token_key = encryption.derive_token_key(collection if approach == "D" else None)
    companion_fields_all = schema.COMPANION_FIELDS.get(collection, [])

    records: list[StoredRecord] = []
    value_to_indices: dict[str, list[int]] = defaultdict(list)
    for _, row in df.iterrows():
        value = str(row[sensitive_field])
        token = encryption.deterministic_token(value, key=token_key)
        patient_token = (
            encryption.deterministic_token(str(row[link_field]), key=token_key) if has_link else None
        )
        payload = encryption.encrypt_payload(_payload_fields(row, {sensitive_field}))
        value_to_indices[value].append(len(records))
        records.append(
            StoredRecord(
                record_id=row["record_id"],
                is_dummy=False,
                token=token,
                patient_token=patient_token,
                plain_value=value,
                plain_patient_code=str(row[link_field]) if has_link else None,
                payload=payload,
                companion_values={f: str(row[f]) for f in companion_fields_all},
            )
        )

    if approach == "B":
        return records

    # C / D: add decoys targeted to flatten the observed frequency of `sensitive_field`
    # (B.4.2), then re-issue every record's (real and decoy) server-visible id from the
    # secret id(i)/isDecoy(i) formula (B.4.1) so the two are indistinguishable on the
    # server.
    value_counts = df[sensitive_field].astype(str).value_counts().to_dict()
    target_counts = decoys.compute_target_counts(
        value_counts, target_ratio=decoy_target_ratio if decoy_target_ratio is not None else config.DECOY_TARGET_RATIO
    )
    companion_fields = schema.COMPANION_FIELDS.get(collection, []) + ([link_field] if has_link else [])

    if approach == "C":
        sampler = decoys.naive_decoy_generator(df, sensitive_field, companion_fields, seed=config.WORKLOAD_SEED)
    else:
        sampler = decoys.conditional_decoy_generator(df, sensitive_field, companion_fields, seed=config.WORKLOAD_SEED)

    id_collection = collection if approach == "D" else None
    counter = 0
    decoy_records: list[StoredRecord] = []

    for value, indices in value_to_indices.items():
        n_real = len(indices)
        n_decoys = target_counts.get(value, 0)

        decoy_rows = sampler(value, n_decoys) if n_decoys > 0 else []
        decoy_idx = 0
        remaining_indices = list(indices)

        for entry in secret_id.iter_ids(n_real=n_real, n_decoy=n_decoys, collection=id_collection, start=counter):
            counter = entry.i + 1
            if entry.is_decoy:
                if decoy_idx >= len(decoy_rows):
                    continue
                row = decoy_rows[decoy_idx]
                decoy_idx += 1
                token = encryption.deterministic_token(value, key=token_key)
                patient_token = (
                    encryption.deterministic_token(str(row[link_field]), key=token_key) if has_link else None
                )
                payload = encryption.encrypt_payload(_payload_fields(pd.Series(row), {sensitive_field}))
                decoy_records.append(
                    StoredRecord(
                        record_id=entry.id_bytes.hex(),
                        is_dummy=True,
                        token=token,
                        patient_token=patient_token,
                        plain_value=value,
                        plain_patient_code=str(row.get(link_field)) if has_link else None,
                        payload=payload,
                        companion_values={f: str(row.get(f)) for f in companion_fields_all},
                    )
                )
            else:
                idx = remaining_indices.pop(0)
                records[idx].record_id = entry.id_bytes.hex()

    return records + decoy_records
