"""Experiment orchestrator (plan section B.10, steps 5-9).

Grid: scale x engine x schema(single|multi) x approach x repeat. `single` schema queries
the `lab_orders` collection alone; `multi` schema loops all three linked collections per
approach/engine and additionally runs the cross-collection linkage attack once per
(scale, engine, approach), logged as one extra row with collection="linkage".

Usage:
    python -m src.experiments.run_experiment
    python -m src.experiments.run_experiment --scales 10000 --repeats 3
    python -m src.experiments.run_experiment --engines mongo --approaches A B C D --schema both
"""
from __future__ import annotations

import argparse
import time

import psutil

from src.core import config, dataset, decoys, encryption, metrics, schema, workload
from src.core.attack import (
    ExecutedQuery,
    apply_realism_filter,
    build_realism_keep_map,
    run_count_attack,
    run_linkage_attack,
)
from src.core.records import prepare_records

ENGINE_FACTORIES = {}


def _get_engine_factories():
    # Imported lazily so `--engines mongo` doesn't require the couchbase/cassandra
    # drivers to be importable (and vice versa), which matters when engines are brought
    # up one at a time (plan verification steps 2-3).
    if not ENGINE_FACTORIES:
        from src.core.adapters.mongo_adapter import MongoAdapter

        ENGINE_FACTORIES["mongo"] = MongoAdapter
        from src.core.adapters.couchbase_adapter import CouchbaseAdapter

        ENGINE_FACTORIES["couchbase"] = CouchbaseAdapter
        from src.core.adapters.cassandra_adapter import CassandraAdapter

        ENGINE_FACTORIES["cassandra"] = CassandraAdapter
        from src.core.adapters.arango_adapter import ArangoAdapter

        ENGINE_FACTORIES["arangodb"] = ArangoAdapter
    return ENGINE_FACTORIES


def run_workload_once(adapter, approach: str, collection: str, queries: list[str], token_key: bytes | None):
    executed = []
    latencies = []
    for value in queries:
        token = None if approach == "A" else encryption.deterministic_token(value, key=token_key)
        qr = adapter.query_equality(approach, collection, value, token)
        latencies.append(qr.latency_ms)
        executed.append(ExecutedQuery(true_value=value, token=token, volume=qr.volume, record_ids=qr.record_ids))
    return executed, latencies


def _empty_row(dataset_source, scale, engine, approach, schema_mode, collection, linkage_accuracy) -> metrics.ResultRow:
    return metrics.ResultRow(
        dataset_source=dataset_source,
        scale=scale,
        engine=engine,
        approach=approach,
        schema=schema_mode,
        collection=collection,
        repeat=0,
        n_queries=0,
        mean_latency_ms=0.0,
        p95_latency_ms=0.0,
        throughput_qps=0.0,
        cpu_percent=0.0,
        storage_mb=0.0,
        ciphertext_expansion_factor=1.0,
        recovery_accuracy=None,
        recovery_accuracy_filtered=None,
        linkage_recovery_accuracy=linkage_accuracy,
        n_unique_tokens=0,
        decoy_target_ratio=None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scales", type=int, nargs="+", default=None,
        help="Defaults to config.SCALE_POINTS (1,000 / 10,000 / 30,000).",
    )
    parser.add_argument(
        "--engines", nargs="+", default=config.DEFAULT_ENGINES,
        choices=["mongo", "couchbase", "cassandra", "arangodb"],
    )
    parser.add_argument("--approaches", nargs="+", default=config.DEFAULT_APPROACHES, choices=["A", "B", "C", "D"])
    parser.add_argument("--schema", default="both", choices=["single", "multi", "both"])
    parser.add_argument("--repeats", type=int, default=config.DEFAULT_REPEATS)
    parser.add_argument("--n-queries", type=int, default=config.DEFAULT_N_QUERIES)
    parser.add_argument(
        "--decoy-ratios", type=float, nargs="+", default=config.DECOY_TARGET_RATIOS,
        help="Swept for approaches C/D only (A/B ignore it): how far each value's count is "
        "padded toward the max value's count (1.0 = fully flattened). Reported as an "
        "independent variable, not a tuned constant -- more flattening lowers recovery but "
        "raises storage/latency overhead.",
    )
    args = parser.parse_args()

    if args.scales is None:
        args.scales = config.SCALE_POINTS

    schema_modes = ["single", "multi"] if args.schema == "both" else [args.schema]
    factories = _get_engine_factories()

    for scale in args.scales:
        print(f"\n=== Scale point: {scale} records ===")
        df, info = dataset.load_scaled_dataset(scale)
        print(f"Dataset source: {info.source} | sensitive field: {info.sensitive_field}")
        collections_df = schema.build_collections(df)

        for engine_name in args.engines:
            adapter = factories[engine_name]()
            try:
                for schema_mode in schema_modes:
                    target_collections = (
                        {"lab_orders": collections_df["lab_orders"]} if schema_mode == "single" else collections_df
                    )
                    baseline_storage: dict[str, float] = {}

                    for approach in args.approaches:
                        # Only C/D actually use decoys, so only they sweep the ratio; A/B run
                        # once each (ratio=None -- storage/security genuinely don't depend on
                        # it for those approaches, so sweeping would just repeat identical work).
                        ratios = args.decoy_ratios if approach in ("C", "D") else [None]
                        stored_records_by_collection = {}

                        for decoy_ratio in ratios:
                            ratio_tag = f" decoy_ratio={decoy_ratio}" if decoy_ratio is not None else ""
                            print(f"\n--- engine={engine_name} schema={schema_mode} approach={approach} scale={scale}{ratio_tag} ---")

                            for coll_name, coll_df in target_collections.items():
                                sensitive_field = schema.QUERY_FIELD.get(coll_name, config.SENSITIVE_FIELD)

                                adapter.setup(approach, coll_name)
                                adapter.bulk_load(approach, coll_name, coll_df, sensitive_field, decoy_ratio)
                                records = prepare_records(coll_df, approach, coll_name, sensitive_field, decoy_ratio)
                                stored_records_by_collection[coll_name] = records

                                storage_mb = adapter.storage_size_mb(approach, coll_name)
                                if approach == "A":
                                    baseline_storage[coll_name] = storage_mb
                                elif coll_name not in baseline_storage:
                                    # This process invocation never ran approach A for this
                                    # collection (e.g. a --approaches C/D-only chunk split off
                                    # to survive an interrupted run) -- query A's storage
                                    # directly rather than silently reporting expansion=1.0x.
                                    # A's collection persists across runs (setup() only drops
                                    # the collection for the approach being processed), so this
                                    # is only unavailable if A itself was never run at all.
                                    baseline_storage[coll_name] = adapter.storage_size_mb("A", coll_name)
                                expansion = (storage_mb / baseline_storage[coll_name]) if baseline_storage.get(coll_name) else 1.0

                                token_key = encryption.derive_token_key(coll_name if approach == "D" else None)
                                queries = workload.load_or_generate_workload(
                                    coll_df, scale, sensitive_field=sensitive_field, n_queries=args.n_queries,
                                    label=f"{schema_mode}_{coll_name}",
                                )
                                value_counts = coll_df[sensitive_field].astype(str).value_counts().to_dict()

                                companion_fields = schema.COMPANION_FIELDS.get(coll_name, [])
                                joint_dist = None
                                keep_map = None
                                if approach in ("C", "D"):
                                    joint_dist = decoys.build_joint_distribution(coll_df, sensitive_field, companion_fields)
                                    keep_map = build_realism_keep_map(records, joint_dist, sensitive_field, companion_fields)

                                for repeat in range(args.repeats):
                                    psutil.cpu_percent(interval=None)
                                    start = time.perf_counter()
                                    executed, latencies = run_workload_once(adapter, approach, coll_name, queries, token_key)
                                    wall_time = time.perf_counter() - start
                                    cpu_percent = psutil.cpu_percent(interval=None)

                                    mean_lat, p95_lat = metrics.latency_summary(latencies)
                                    throughput = len(queries) / wall_time if wall_time > 0 else 0.0

                                    attack_result = run_count_attack(approach, executed, value_counts)
                                    recovery_accuracy_filtered = None
                                    if keep_map is not None:
                                        filtered_executed = apply_realism_filter(executed, keep_map)
                                        recovery_accuracy_filtered = run_count_attack(approach, filtered_executed, value_counts).recovery_accuracy

                                    row = metrics.ResultRow(
                                        dataset_source=info.source,
                                        scale=scale,
                                        engine=engine_name,
                                        approach=approach,
                                        schema=schema_mode,
                                        collection=coll_name,
                                        repeat=repeat,
                                        n_queries=len(queries),
                                        mean_latency_ms=mean_lat,
                                        p95_latency_ms=p95_lat,
                                        throughput_qps=throughput,
                                        cpu_percent=cpu_percent,
                                        storage_mb=storage_mb,
                                        ciphertext_expansion_factor=expansion,
                                        recovery_accuracy=attack_result.recovery_accuracy,
                                        recovery_accuracy_filtered=recovery_accuracy_filtered,
                                        linkage_recovery_accuracy=None,
                                        n_unique_tokens=attack_result.n_unique_tokens,
                                        decoy_target_ratio=decoy_ratio,
                                    )
                                    metrics.append_result(row)
                                    filt = f" filtered={recovery_accuracy_filtered:.1%}" if recovery_accuracy_filtered is not None else ""
                                    print(
                                        f"  [{coll_name}] repeat {repeat}: lat={mean_lat:.3f}ms p95={p95_lat:.3f}ms "
                                        f"tp={throughput:.1f}qps cpu={cpu_percent:.1f}% storage={storage_mb:.2f}MB "
                                        f"expansion={expansion:.2f}x recovery={attack_result.recovery_accuracy:.1%}{filt}"
                                    )

                        # Linkage doesn't depend on decoy_target_ratio (it scores real records'
                        # patient_token equality only, decoys are excluded via is_dummy) -- run
                        # it once per approach using whichever ratio's records are in hand (the
                        # last one from the loop above; for A/B there's only ever one).
                        if schema_mode == "multi" and len(stored_records_by_collection) == len(config.COLLECTIONS):
                            linkage_result = run_linkage_attack(approach, stored_records_by_collection)
                            metrics.append_result(
                                _empty_row(info.source, scale, engine_name, approach, schema_mode, "linkage", linkage_result.linkage_recovery_accuracy)
                            )
                            print(f"  [linkage] approach={approach}: recovery={linkage_result.linkage_recovery_accuracy:.1%}")
            finally:
                adapter.close()

    print(f"\nDone. Results appended to {metrics.RESULTS_CSV}")


if __name__ == "__main__":
    main()
