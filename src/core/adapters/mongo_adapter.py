from __future__ import annotations

import time

from bson.binary import Binary
from pymongo import ASCENDING, MongoClient

from src.core import config
from src.core.adapters.base import QueryResult, StorageAdapter
from src.core.records import prepare_records


def _name(approach: str, collection: str) -> str:
    return f"{approach}_{collection}"


class MongoAdapter(StorageAdapter):
    engine_name = "mongo"

    def __init__(self):
        self.client = MongoClient(config.MONGO_URI)
        self.db = self.client[config.MONGO_DB]

    def setup(self, approach: str, collection: str) -> None:
        name = _name(approach, collection)
        self.db.drop_collection(name)
        coll = self.db[name]
        if approach == "A":
            coll.create_index([("sensitive_value", ASCENDING)])
        else:
            coll.create_index([("token", ASCENDING)])
            coll.create_index([("patient_token", ASCENDING)])

    def bulk_load(
        self, approach: str, collection: str, df, sensitive_field: str, decoy_target_ratio: float | None = None
    ) -> None:
        coll = self.db[_name(approach, collection)]
        records = prepare_records(df, approach, collection, sensitive_field, decoy_target_ratio)
        docs = []
        for r in records:
            if approach == "A":
                docs.append(
                    {
                        "_id": r.record_id,
                        "sensitive_value": r.plain_value,
                        "patient_value": r.plain_patient_code,
                    }
                )
            else:
                docs.append(
                    {
                        "_id": r.record_id,
                        "token": Binary(r.token),
                        "patient_token": Binary(r.patient_token) if r.patient_token else None,
                        "payload": Binary(r.payload) if r.payload else None,
                    }
                )
        if docs:
            coll.insert_many(docs, ordered=False)

    def query_equality(
        self, approach: str, collection: str, value: str, token: bytes | None = None
    ) -> QueryResult:
        coll = self.db[_name(approach, collection)]
        start = time.perf_counter()
        if approach == "A":
            cursor = coll.find({"sensitive_value": value}, {"_id": 1})
        else:
            cursor = coll.find({"token": Binary(token)}, {"_id": 1})
        ids = [doc["_id"] for doc in cursor]
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryResult(latency_ms=latency_ms, volume=len(ids), record_ids=ids)

    def storage_size_mb(self, approach: str, collection: str) -> float:
        stats = self.db.command("collStats", _name(approach, collection))
        total_bytes = stats.get("size", 0) + stats.get("totalIndexSize", 0)
        return total_bytes / (1024 * 1024)

    def close(self) -> None:
        self.client.close()
