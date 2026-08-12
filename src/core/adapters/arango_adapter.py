"""ArangoDB adapter (plan B.9/B.10 step 4). Uses the `python-arango` driver.

One collection per `{approach}_{collection}` (same naming scheme as the Mongo adapter),
with a persistent (B-tree-like) index on the queried field for equality lookups. ArangoDB
documents are JSON, not BSON, so ciphertext `bytes` fields are base64-encoded before
storage and decoded back on read, same as the Couchbase adapter.

Database creation is done lazily inside `__init__` (create-if-not-exists) so the adapter
self-heals across `docker compose down/up` without a separate init script, matching the
other two adapters' convention.
"""
from __future__ import annotations

import base64
import time

from arango import ArangoClient
from arango.exceptions import CollectionCreateError, DatabaseCreateError, IndexCreateError

from src.core import config
from src.core.adapters.base import QueryResult, StorageAdapter
from src.core.records import prepare_records


def _name(approach: str, collection: str) -> str:
    return f"{approach}_{collection}"


def _b64(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode() if data is not None else None


def _unb64(data: str | None) -> bytes | None:
    return base64.b64decode(data) if data is not None else None


class ArangoAdapter(StorageAdapter):
    engine_name = "arangodb"

    def __init__(self):
        self.client = ArangoClient(hosts=config.ARANGO_URL)
        sys_db = self.client.db("_system", username=config.ARANGO_USER, password=config.ARANGO_PASSWORD)
        try:
            if not sys_db.has_database(config.ARANGO_DB):
                sys_db.create_database(config.ARANGO_DB)
        except DatabaseCreateError:
            pass
        self.db = self.client.db(config.ARANGO_DB, username=config.ARANGO_USER, password=config.ARANGO_PASSWORD)

    def _collection(self, approach: str, collection: str):
        name = _name(approach, collection)
        if not self.db.has_collection(name):
            try:
                self.db.create_collection(name)
            except CollectionCreateError:
                pass
        return self.db.collection(name)

    def setup(self, approach: str, collection: str) -> None:
        name = _name(approach, collection)
        if self.db.has_collection(name):
            self.db.delete_collection(name)
        coll = self.db.create_collection(name)
        index_field = "sensitive_value" if approach == "A" else "token"
        try:
            coll.add_index({"type": "persistent", "fields": [index_field]})
        except IndexCreateError:
            pass
        if approach != "A":
            try:
                coll.add_index({"type": "persistent", "fields": ["patient_token"]})
            except IndexCreateError:
                pass

    def bulk_load(
        self, approach: str, collection: str, df, sensitive_field: str, decoy_target_ratio: float | None = None
    ) -> None:
        coll = self._collection(approach, collection)
        records = prepare_records(df, approach, collection, sensitive_field, decoy_target_ratio)
        docs = []
        for r in records:
            if approach == "A":
                docs.append({"_key": r.record_id, "sensitive_value": r.plain_value, "patient_value": r.plain_patient_code})
            else:
                docs.append(
                    {
                        "_key": r.record_id,
                        "token": _b64(r.token),
                        "patient_token": _b64(r.patient_token),
                        "payload": _b64(r.payload),
                    }
                )
        if docs:
            coll.insert_many(docs, overwrite_mode="ignore")

    def query_equality(
        self, approach: str, collection: str, value: str, token: bytes | None = None
    ) -> QueryResult:
        name = _name(approach, collection)
        start = time.perf_counter()
        if approach == "A":
            cursor = self.db.aql.execute(
                "FOR doc IN @@coll FILTER doc.sensitive_value == @val RETURN doc._key",
                bind_vars={"@coll": name, "val": value},
            )
        else:
            cursor = self.db.aql.execute(
                "FOR doc IN @@coll FILTER doc.token == @val RETURN doc._key",
                bind_vars={"@coll": name, "val": _b64(token)},
            )
        ids = list(cursor)
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryResult(latency_ms=latency_ms, volume=len(ids), record_ids=ids)

    def storage_size_mb(self, approach: str, collection: str) -> float:
        name = _name(approach, collection)
        if not self.db.has_collection(name):
            return 0.0
        try:
            stats = self.db.collection(name).statistics()
            figures = stats.get("figures", stats)
            docs_size = figures.get("documentsSize", 0) or 0
            index_size = 0
            indexes = figures.get("indexes")
            if isinstance(indexes, dict):
                index_size = indexes.get("size", 0) or 0
            return (docs_size + index_size) / (1024 * 1024)
        except Exception:
            return 0.0

    def close(self) -> None:
        pass
