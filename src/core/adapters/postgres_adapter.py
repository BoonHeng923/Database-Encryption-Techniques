from __future__ import annotations

import time

import psycopg2
import psycopg2.extras

from src.core import config
from src.core.adapters.base import QueryResult, StorageAdapter
from src.core.records import prepare_records

_TABLE = {"A": "approach_a", "B": "approach_b", "C": "approach_c"}


class PostgresAdapter(StorageAdapter):
    engine_name = "postgres"

    def __init__(self):
        self.conn = psycopg2.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        )
        self.conn.autocommit = True

    def setup(self, approach: str) -> None:
        table = _TABLE[approach]
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            if approach == "A":
                cur.execute(
                    f"""
                    CREATE TABLE {table} (
                        record_id TEXT PRIMARY KEY,
                        sensitive_value TEXT NOT NULL
                    )
                    """
                )
                cur.execute(f"CREATE INDEX idx_{table}_value ON {table} (sensitive_value)")
            else:
                cur.execute(
                    f"""
                    CREATE TABLE {table} (
                        record_id TEXT PRIMARY KEY,
                        token BYTEA NOT NULL,
                        payload BYTEA,
                        is_dummy BOOLEAN NOT NULL DEFAULT FALSE
                    )
                    """
                )
                cur.execute(f"CREATE INDEX idx_{table}_token ON {table} (token)")

    def bulk_load(self, approach: str, df, sensitive_field: str) -> None:
        table = _TABLE[approach]
        records = prepare_records(df, approach, sensitive_field)
        with self.conn.cursor() as cur:
            if approach == "A":
                rows = [(r.record_id, r.plain_value) for r in records]
                psycopg2.extras.execute_values(
                    cur, f"INSERT INTO {table} (record_id, sensitive_value) VALUES %s", rows
                )
            else:
                rows = [
                    (r.record_id, psycopg2.Binary(r.token), psycopg2.Binary(r.payload) if r.payload else None, r.is_dummy)
                    for r in records
                ]
                psycopg2.extras.execute_values(
                    cur,
                    f"INSERT INTO {table} (record_id, token, payload, is_dummy) VALUES %s",
                    rows,
                )
        self.conn.commit()

    def query_equality(self, approach: str, value: str, token: bytes | None = None) -> QueryResult:
        table = _TABLE[approach]
        with self.conn.cursor() as cur:
            start = time.perf_counter()
            if approach == "A":
                cur.execute(f"SELECT record_id FROM {table} WHERE sensitive_value = %s", (value,))
            else:
                cur.execute(f"SELECT record_id FROM {table} WHERE token = %s", (psycopg2.Binary(token),))
            rows = cur.fetchall()
            latency_ms = (time.perf_counter() - start) * 1000
        return QueryResult(latency_ms=latency_ms, volume=len(rows), record_ids=[r[0] for r in rows])

    def storage_size_mb(self, approach: str) -> float:
        table = _TABLE[approach]
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_total_relation_size(%s)", (table,))
            (size_bytes,) = cur.fetchone()
        return size_bytes / (1024 * 1024)

    def close(self) -> None:
        self.conn.close()
