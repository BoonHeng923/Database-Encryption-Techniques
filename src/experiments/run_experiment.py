"""Experiment orchestrator (plan section B.10, steps 5-9, Phase 1 scope: Postgres + Mongo).

Usage:
    python -m src.experiments.run_experiment
    python -m src.experiments.run_experiment --scales 10000 100000 --repeats 3
    python -m src.experiments.run_experiment --engines postgres
"""
from __future__ import annotations

import argparse
import time

import psutil

from src.core import config, dataset, encryption, metrics, workload
from src.core.attack import ExecutedQuery, run_count_attack

ENGINE_FACTORIES = {}


def _get_engine_factories():
    # Imported lazily so `--engines postgres` doesn't require pymongo to be importable
    # (and vice versa), which matters when engines are brought up one at a time.
    if not ENGINE_FACTORIES:
        from src.core.adapters.postgres_adapter import PostgresAdapter

        ENGINE_FACTORIES["postgres"] = PostgresAdapter
        from src.core.adapters.mongo_adapter import MongoAdapter

        ENGINE_FACTORIES["mongo"] = MongoAdapter
    return ENGINE_FACTORIES


def run_workload_once(adapter, approach: str, queries: list[str]) -> tuple[list[ExecutedQuery], list[float]]:
    executed = []
    latencies = []
    for value in queries:
        token = None if approach == "A" else encryption.deterministic_token(value)
        qr = adapter.query_equality(approach, value, token)
        latencies.append(qr.latency_ms)
        executed.append(ExecutedQuery(true_value=value, token=token, volume=qr.volume))
    return executed, latencies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scales", type=int, nargs="+", default=None,
        help="Defaults to 1,000 / 10,000 / the full dataset size (plan B.5).",
    )
    parser.add_argument("--engines", nargs="+", default=config.DEFAULT_ENGINES, choices=["postgres", "mongo"])
    parser.add_argument("--approaches", nargs="+", default=config.DEFAULT_APPROACHES, choices=["A", "B", "C"])
    parser.add_argument("--repeats", type=int, default=config.DEFAULT_REPEATS)
    parser.add_argument("--n-queries", type=int, default=config.DEFAULT_N_QUERIES)
    args = parser.parse_args()

    if args.scales is None:
        args.scales = config.SMALL_SCALE_POINTS + [dataset.full_dataset_size()]

    factories = _get_engine_factories()

    for scale in args.scales:
        print(f"\n=== Scale point: {scale} records ===")
        df, info = dataset.load_scaled_dataset(scale)
        print(f"Dataset source: {info.source} | sensitive field: {info.sensitive_field} | "
              f"value counts: {info.value_counts}")
        queries = workload.load_or_generate_workload(df, scale, n_queries=args.n_queries)

        for engine_name in args.engines:
            adapter = factories[engine_name]()
            baseline_storage_mb = None
            try:
                for approach in args.approaches:
                    print(f"\n--- engine={engine_name} approach={approach} scale={scale} ---")
                    adapter.setup(approach)
                    adapter.bulk_load(approach, df, config.SENSITIVE_FIELD)
                    storage_mb = adapter.storage_size_mb(approach)
                    if approach == "A":
                        baseline_storage_mb = storage_mb
                    expansion = (storage_mb / baseline_storage_mb) if baseline_storage_mb else 1.0

                    for repeat in range(args.repeats):
                        psutil.cpu_percent(interval=None)  # prime the internal counter
                        start = time.perf_counter()
                        executed, latencies = run_workload_once(adapter, approach, queries)
                        wall_time = time.perf_counter() - start
                        cpu_percent = psutil.cpu_percent(interval=None)

                        mean_lat, p95_lat = metrics.latency_summary(latencies)
                        throughput = len(queries) / wall_time if wall_time > 0 else 0.0

                        attack_result = run_count_attack(approach, executed, info.value_counts)

                        row = metrics.ResultRow(
                            dataset_source=info.source,
                            scale=scale,
                            engine=engine_name,
                            approach=approach,
                            repeat=repeat,
                            n_queries=len(queries),
                            mean_latency_ms=mean_lat,
                            p95_latency_ms=p95_lat,
                            throughput_qps=throughput,
                            cpu_percent=cpu_percent,
                            storage_mb=storage_mb,
                            ciphertext_expansion_factor=expansion,
                            recovery_accuracy=attack_result.recovery_accuracy,
                            n_unique_tokens=attack_result.n_unique_tokens,
                        )
                        metrics.append_result(row)
                        print(
                            f"  repeat {repeat}: lat={mean_lat:.3f}ms p95={p95_lat:.3f}ms "
                            f"tp={throughput:.1f}qps cpu={cpu_percent:.1f}% storage={storage_mb:.2f}MB "
                            f"expansion={expansion:.2f}x recovery={attack_result.recovery_accuracy:.1%}"
                        )
            finally:
                adapter.close()

    print(f"\nDone. Results appended to {metrics.RESULTS_CSV}")


if __name__ == "__main__":
    main()
