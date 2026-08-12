"""Couchbase adapter (plan B.9/B.10 step 4). Uses the `couchbase` Python SDK.

Layout: one bucket (`encbench`), one scope per collection (`patients`/`lab_orders`/
`billing`), and one Couchbase collection per approach inside that scope, so a storage
unit is addressed as bucket.`{collection}`.`{approach}` -- same `{approach}_{collection}`
identity the other engines use, just split across scope/collection instead of name
concatenation because Couchbase scopes/collections are first-class.

Cluster/bucket/scope/collection creation is all done lazily inside `setup()` (create-if-
not-exists, exceptions from "already exists" swallowed) so the adapter self-heals across
`docker compose down/up` without a fragile compose-time init script (plan requirement).

Couchbase documents are JSON, not BSON, so ciphertext `bytes` fields are base64-encoded
before storage and decoded back on read.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from datetime import timedelta

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    CollectionAlreadyExistsException,
    CouchbaseException,
    ScopeAlreadyExistsException,
)
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.collections import CollectionSpec
from couchbase.options import ClusterOptions

from src.core import config
from src.core.adapters.base import QueryResult, StorageAdapter
from src.core.records import prepare_records


def _b64(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode() if data is not None else None


def _unb64(data: str | None) -> bytes | None:
    return base64.b64decode(data) if data is not None else None


class CouchbaseAdapter(StorageAdapter):
    engine_name = "couchbase"

    def __init__(self):
        self._ensure_cluster_initialized()
        self._ensure_index_storage_mode()
        self._ensure_alternate_address()
        self.cluster = Cluster(
            f"couchbase://{config.COUCHBASE_HOST}",
            ClusterOptions(PasswordAuthenticator(config.COUCHBASE_USER, config.COUCHBASE_PASSWORD)),
        )
        try:
            self.cluster.wait_until_ready(timedelta(seconds=30))
        except CouchbaseException:
            pass
        self._ensure_bucket()
        self.bucket = self.cluster.bucket(config.COUCHBASE_BUCKET)

    def _ensure_cluster_initialized(self) -> None:
        # A freshly-started Couchbase container has no admin user and no services
        # enabled until `cluster-init` runs once -- do it here via the REST API so the
        # adapter self-heals on a brand new container without a separate compose-time
        # init script. If the cluster is already initialized this call fails and is
        # swallowed.
        try:
            payload = urllib.parse.urlencode(
                {
                    "username": config.COUCHBASE_USER,
                    "password": config.COUCHBASE_PASSWORD,
                    "services": "kv,n1ql,index",
                    "memoryQuota": "512",
                    "indexMemoryQuota": "256",
                    "port": "8091",
                    "sendStats": "false",
                }
            ).encode()
            req = urllib.request.Request(
                f"http://{config.COUCHBASE_HOST}:8091/clusterInit", data=payload, method="POST"
            )
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass

    def _ensure_index_storage_mode(self) -> None:
        # A freshly cluster-init'd node has the index service enabled but no storage
        # mode chosen -- every CREATE INDEX fails with "Please Set Indexer Storage Mode
        # Before Create Index" until this is set once. Left unset, setup()'s CREATE INDEX
        # calls fail silently (caught below) and every query silently falls back to a full
        # collection scan -- the actual cause of Couchbase's ~150-250ms uniform query
        # latency observed before this fix (confirmed by manually setting this and timing
        # the same query: 150ms+ -> ~12ms once an index actually exists). Community
        # Edition only supports "forestdb"; Enterprise's plasma/memory_optimized aren't
        # available here. Self-heals every start, same pattern as the other _ensure_*.
        try:
            payload = urllib.parse.urlencode({"storageMode": "forestdb"}).encode()
            req = urllib.request.Request(
                f"http://{config.COUCHBASE_HOST}:8091/settings/indexes", data=payload, method="POST"
            )
            auth = base64.b64encode(f"{config.COUCHBASE_USER}:{config.COUCHBASE_PASSWORD}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass

    def _ensure_alternate_address(self) -> None:
        # Inside the Docker network the node advertises its container hostname/IP for
        # the query/index/FTS services; a client connecting from the host (COUCHBASE_HOST
        # =localhost, port-mapped 1:1) can reach KV/mgmt via that container-internal
        # bootstrap but N1QL/query routing then fails with ServiceUnavailableException
        # because it tries to dial the unreachable internal address. Registering an
        # "external" alternate address (self-heals every start, like cluster-init above)
        # fixes this without a separate compose-time init script.
        try:
            payload = urllib.parse.urlencode(
                {"hostname": config.COUCHBASE_HOST, "mgmt": "8091", "kv": "11210", "capi": "8092", "n1ql": "8093", "fts": "8094"}
            ).encode()
            req = urllib.request.Request(
                f"http://{config.COUCHBASE_HOST}:8091/node/controller/setupAlternateAddresses/external",
                data=payload, method="PUT",
            )
            auth = base64.b64encode(f"{config.COUCHBASE_USER}:{config.COUCHBASE_PASSWORD}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            urllib.request.urlopen(req, timeout=15)
        except Exception:
            pass

    def _ensure_bucket(self) -> None:
        bucket_mgr = self.cluster.buckets()
        try:
            bucket_mgr.create_bucket(CreateBucketSettings(name=config.COUCHBASE_BUCKET, ram_quota_mb=256))
        except BucketAlreadyExistsException:
            pass
        except CouchbaseException:
            pass

    def _ensure_scope_collection(self, collection: str, approach: str) -> None:
        coll_mgr = self.bucket.collections()
        try:
            coll_mgr.create_scope(collection)
        except ScopeAlreadyExistsException:
            pass
        except CouchbaseException:
            pass
        try:
            coll_mgr.create_collection(CollectionSpec(approach, scope_name=collection))
        except CollectionAlreadyExistsException:
            pass
        except CouchbaseException:
            pass

    def _coll(self, approach: str, collection: str):
        return self.bucket.scope(collection).collection(approach)

    def setup(self, approach: str, collection: str) -> None:
        self._ensure_scope_collection(collection, approach)
        keyspace = f"`{config.COUCHBASE_BUCKET}`.`{collection}`.`{approach}`"
        try:
            self.cluster.query(f"DELETE FROM {keyspace}").execute()
        except CouchbaseException:
            pass
        index_field = "sensitive_value" if approach == "A" else "token"
        try:
            self.cluster.query(
                f"CREATE INDEX idx_{approach}_{collection}_val ON {keyspace}({index_field})"
            ).execute()
        except CouchbaseException:
            pass
        if approach != "A":
            try:
                self.cluster.query(
                    f"CREATE INDEX idx_{approach}_{collection}_patient ON {keyspace}(patient_token)"
                ).execute()
            except CouchbaseException:
                pass

    def bulk_load(
        self, approach: str, collection: str, df, sensitive_field: str, decoy_target_ratio: float | None = None
    ) -> None:
        coll = self._coll(approach, collection)
        records = prepare_records(df, approach, collection, sensitive_field, decoy_target_ratio)
        for r in records:
            if approach == "A":
                doc = {"sensitive_value": r.plain_value, "patient_value": r.plain_patient_code}
            else:
                doc = {
                    "token": _b64(r.token),
                    "patient_token": _b64(r.patient_token),
                    "payload": _b64(r.payload),
                }
            coll.upsert(r.record_id, doc)

        # GSI indexes are eventually consistent: a query issued immediately after these
        # upserts can race the *specific secondary index* query_equality() uses and
        # undercount just-written documents, even though the data itself is already
        # durably stored (confirmed by testing: REQUEST_PLUS alone did not reliably wait
        # long enough here). Poll the exact same index-driven count the equality queries
        # will use until it reaches the expected total (or a generous timeout), so every
        # measured query in this run starts from a fully caught-up index -- the workload
        # itself still uses default (fast, NOT_BOUNDED) consistency, so latency numbers
        # reflect a warm index, not this one-time catch-up.
        keyspace = f"`{config.COUCHBASE_BUCKET}`.`{collection}`.`{approach}`"
        index_field = "sensitive_value" if approach == "A" else "token"
        expected = len(records)
        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            try:
                row = self.cluster.query(f"SELECT RAW COUNT(*) FROM {keyspace} WHERE {index_field} IS NOT MISSING").execute()
                n_indexed = list(row)[0] if row else 0
            except CouchbaseException:
                n_indexed = 0
            if n_indexed >= expected:
                break
            time.sleep(0.2)

    def query_equality(
        self, approach: str, collection: str, value: str, token: bytes | None = None
    ) -> QueryResult:
        keyspace = f"`{config.COUCHBASE_BUCKET}`.`{collection}`.`{approach}`"
        if approach == "A":
            stmt = f"SELECT META().id AS id FROM {keyspace} WHERE sensitive_value = $val"
            params = {"val": value}
        else:
            stmt = f"SELECT META().id AS id FROM {keyspace} WHERE token = $val"
            params = {"val": _b64(token)}
        start = time.perf_counter()
        rows = list(self.cluster.query(stmt, **params))
        latency_ms = (time.perf_counter() - start) * 1000
        ids = [row["id"] for row in rows]
        return QueryResult(latency_ms=latency_ms, volume=len(ids), record_ids=ids)

    def storage_size_mb(self, approach: str, collection: str) -> float:
        # Couchbase's cluster-management stats API reports size at the *bucket* level,
        # not per scope/collection, so this is the whole `encbench` bucket's data usage,
        # not just this approach/collection's -- a documented limitation (like Cassandra's
        # approximate estimate below) rather than an exact per-unit figure.
        try:
            req = urllib.request.Request(
                f"http://{config.COUCHBASE_HOST}:8091/pools/default/buckets/{config.COUCHBASE_BUCKET}"
            )
            auth = base64.b64encode(f"{config.COUCHBASE_USER}:{config.COUCHBASE_PASSWORD}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            used_bytes = data.get("basicStats", {}).get("dataUsed", 0)
            return used_bytes / (1024 * 1024)
        except Exception:
            return 0.0

    def close(self) -> None:
        pass
