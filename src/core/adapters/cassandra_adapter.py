"""Cassandra adapter (plan B.9/B.10 step 4). Uses `cassandra-driver`, CQL, and a
secondary index on `token_val` (and `sensitive_value` for Approach A) for equality
lookups (`token` itself is a reserved CQL keyword, hence the `_val` suffix).

Keyspace `encbench` is created if missing (SimpleStrategy, RF=1 -- a single-node dev
cluster, matching the other two engines' single-container setup). One table per
`{approach}_{collection}`.
"""
from __future__ import annotations

import time

# cassandra-driver picks its default async connection class at import time from
# {gevent, eventlet, libev, asyncore}: libev needs a C extension not built on this
# platform and asyncore was removed in Python 3.12, so neither works out of the box.
# GeventConnection's read loop needs the full gevent monkey-patch (socket alone leaves
# the connection's internal event/threading wait incompatible with gevent's hub and the
# control connection times out) -- this does mean pymongo/couchbase sockets in the same
# process become gevent-cooperative too if cassandra is used alongside them, which is
# the standard, supported way of mixing gevent-based drivers.
import gevent.monkey

gevent.monkey.patch_all()

from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
from cassandra.io.geventreactor import GeventConnection
from cassandra.query import dict_factory

from src.core import config
from src.core.adapters.base import QueryResult, StorageAdapter
from src.core.records import prepare_records


def _table(approach: str, collection: str) -> str:
    return f"{approach}_{collection}".lower()


class CassandraAdapter(StorageAdapter):
    engine_name = "cassandra"

    def __init__(self):
        self.cluster = Cluster(
            contact_points=config.CASSANDRA_CONTACT_POINTS,
            port=config.CASSANDRA_PORT,
            connection_class=GeventConnection,
        )
        self.session = self.cluster.connect()
        self.session.row_factory = dict_factory
        self.session.execute(
            f"CREATE KEYSPACE IF NOT EXISTS {config.CASSANDRA_KEYSPACE} "
            "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
        )
        self.session.set_keyspace(config.CASSANDRA_KEYSPACE)

    def setup(self, approach: str, collection: str) -> None:
        table = _table(approach, collection)
        self.session.execute(f"DROP TABLE IF EXISTS {table}")
        if approach == "A":
            self.session.execute(
                f"CREATE TABLE {table} (record_id text PRIMARY KEY, sensitive_value text, patient_value text)"
            )
            self.session.execute(f"CREATE INDEX ON {table} (sensitive_value)")
        else:
            # `token` is a reserved CQL keyword (the ring-token function), so the
            # equality column is named `token_val` here to avoid a syntax error.
            self.session.execute(
                f"CREATE TABLE {table} (record_id text PRIMARY KEY, token_val blob, patient_token blob, payload blob)"
            )
            self.session.execute(f"CREATE INDEX ON {table} (token_val)")

    def bulk_load(
        self, approach: str, collection: str, df, sensitive_field: str, decoy_target_ratio: float | None = None
    ) -> None:
        table = _table(approach, collection)
        records = prepare_records(df, approach, collection, sensitive_field, decoy_target_ratio)
        if not records:
            return
        if approach == "A":
            stmt = self.session.prepare(f"INSERT INTO {table} (record_id, sensitive_value, patient_value) VALUES (?, ?, ?)")
            params = [(r.record_id, r.plain_value, r.plain_patient_code) for r in records]
        else:
            stmt = self.session.prepare(
                f"INSERT INTO {table} (record_id, token_val, patient_token, payload) VALUES (?, ?, ?, ?)"
            )
            params = [(r.record_id, r.token, r.patient_token, r.payload) for r in records]
        execute_concurrent_with_args(self.session, stmt, params, concurrency=100)

    def query_equality(
        self, approach: str, collection: str, value: str, token: bytes | None = None
    ) -> QueryResult:
        table = _table(approach, collection)
        start = time.perf_counter()
        if approach == "A":
            rows = self.session.execute(f"SELECT record_id FROM {table} WHERE sensitive_value = %s", (value,))
        else:
            rows = self.session.execute(f"SELECT record_id FROM {table} WHERE token_val = %s", (token,))
        ids = [row["record_id"] for row in rows]
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryResult(latency_ms=latency_ms, volume=len(ids), record_ids=ids)

    def storage_size_mb(self, approach: str, collection: str) -> float:
        # `nodetool tablestats` isn't reachable from the app process/container in this
        # setup (it requires JMX access to the Cassandra node itself), so storage is
        # approximated here as row_count x average serialized row size from a sample --
        # documented as an estimate, not an exact on-disk figure.
        table = _table(approach, collection)
        count_row = self.session.execute(f"SELECT COUNT(*) AS n FROM {table}").one()
        n = count_row["n"] if count_row else 0
        if n == 0:
            return 0.0
        sample = self.session.execute(f"SELECT * FROM {table} LIMIT 200")
        sizes = []
        for row in sample:
            size = 0
            for v in row.values():
                if v is None:
                    continue
                size += len(v) if isinstance(v, (bytes, str)) else 8
            sizes.append(size)
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        return (n * avg_size) / (1024 * 1024)

    def close(self) -> None:
        self.cluster.shutdown()
