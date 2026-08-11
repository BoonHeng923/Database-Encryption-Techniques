# Database-Encryption-Techniques — Phase 1 (PostgreSQL + MongoDB)

Implements plan section B (Beyond Confidentiality benchmark): builds the same dataset
three ways — **A** plaintext, **B** deterministic/property-preserving encryption, **C**
leakage-reduced (volume-hiding) — on PostgreSQL and MongoDB, replays one identical query
workload against all combinations, runs the same leakage-abuse (count) attack against
each, and reports security (recovery accuracy) and performance (latency, throughput,
CPU, storage) side by side.

MySQL, MariaDB, Couchbase, and Cassandra (plan Phase 2) are not yet implemented — the
`StorageAdapter` interface in `src/core/adapters/base.py` is what a new engine
implements; everything else (encryption, workload, attack, metrics, report) is shared
and does not change.

## Project layout

```
src/core/            shared, engine-independent pipeline
  config.py           env-driven configuration
  dataset.py           dataset loader + seeded sub-sampling (1k / 10k / full)
  encryption.py         AES-SIV deterministic token + AES-GCM payload encryption
  records.py             turns a dataframe into per-approach stored rows (incl. C's padding)
  workload.py           seeded, skewed query workload generator
  attack.py               count-attack (leakage-abuse) implementation
  metrics.py                result-row schema / CSV writer
  adapters/
    base.py                StorageAdapter interface
    postgres_adapter.py     PostgreSQL implementation
    mongo_adapter.py         MongoDB implementation
src/experiments/run_experiment.py   orchestrates the full A/B/C x engine x scale grid
src/analysis/
  dataset_profile.py    B.5.1 dataset sanity check (run this first)
  generate_report.py    turns results/raw_results.csv into the B.8 tables/figures
data/raw/              adult_inpatient_patient_portal_data.xlsx (the real dataset)
data/processed/        dataset_cache.csv (fast-reload cache), per-scale workload files
results/                raw_results.csv, tables/*.md, figures/*.png
docker-compose.yml      Postgres + MongoDB containers (+ optional app container)
```

## Databases: Dockerized, already running

This machine also runs **native** PostgreSQL (service `postgresql-x64-18`, port 5432)
and **native** MongoDB (service `MongoDB`, port 27017) from earlier setup — those are
left untouched. The project's actual backend is now the two Docker containers below,
mapped to different host ports so both can coexist:

| Service | Container port | Host port | Credentials |
|---|---|---|---|
| `encbench_postgres` | 5432 | **5433** | `encbench_user` / `encbench_pass`, db `encbench` |
| `encbench_mongo` | 27017 | **27018** | `encbench_user` / `encbench_pass`, db `encbench` (auth required — root/admin creds are separate and not used by the app) |

Both are already up and verified working end-to-end (Postgres via `psycopg2`, Mongo via
`pymongo`, auth enforced correctly). `.env` already points at them.

To bring them up again after a reboot / `docker compose down`:
```
docker compose up -d postgres mongo
docker compose ps          # both should show "healthy"
```

To stop them: `docker compose down` (add `-v` only if you want to also delete the
stored data volumes — don't do this if you have results you still need reproduced).

If you eventually want the whole pipeline running inside Docker too (not just the
databases), `docker-compose.yml` already defines an `app` service — build and run it
with `docker compose run --rm app python -m src.experiments.run_experiment`. It talks to
the containers over the internal Docker network (`postgres:5432` / `mongo:27017`), so it
doesn't need the host-port remap `.env` uses.

## Dataset

The real dataset is in place: `data/raw/adult_inpatient_patient_portal_data.xlsx`
(826,843 de-identified inpatient diagnostic-test records). First load parses the Excel
file once (~70s) and caches it as `data/processed/dataset_cache.csv` for fast reloads
after that — delete the cache file if you ever replace the source `.xlsx`.

**Sensitive/attack-target field: `specific_diagnostic_test`** (297 distinct test names).
This was chosen over the other categorical fields in the file (`diagnostic_test_
category`, `race_category`, `age_category`) via the required B.5.1 sanity check — see
below.

If the `.xlsx` file is ever missing, the pipeline falls back to a small synthetic
generator with the same schema so it stays runnable, but say so explicitly if any
numbers in your report came from the fallback (`dataset_source` column in
`results/raw_results.csv` records which one was used for every row).

### Run the dataset sanity check first (plan B.5.1 — required gate)

```
./.venv/Scripts/python.exe -m src.analysis.dataset_profile
```

Writes `results/tables/dataset_profile.md` (distinct-value counts, skew indicators,
null rate, and confirmation that skew survives sub-sampling at 1k/10k) and histogram
figures to `results/figures/`. This is what justifies the field choice in your report —
paste the table and the "chosen field" reasoning directly into Methodology.

## Scale points

Per the updated plan: **1,000 / 10,000 / full dataset (826,843)**, sub-sampled without
replacement with a fixed seed (not the earlier 10k/100k/500k bootstrap scheme). The full
dataset point is resolved dynamically from whatever file is actually in `data/raw/`, so
it isn't hardcoded.

## Python environment

The global Python on this machine has a broken `pip` install path for the `cryptography`
package's build dependency (`cffi`) — a pre-existing environment issue, not something
this project caused. A virtualenv avoids it and is already set up in `.venv/`:

```
python -m venv .venv                      # already done
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # already done
```

Use `./.venv/Scripts/python.exe` for every command below.

## Encryption key

`.env` ships with `ENC_MASTER_KEY_B64` blank, which falls back to a fixed demo key
(`config.py`) — fine for development, **not** for results going into the report, since
anyone reading the repo would know the key. Before your final run:

```
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

and paste the output into `.env` as `ENC_MASTER_KEY_B64=...`.

## Running the benchmark

```
# 1. Sanity check (once)
./.venv/Scripts/python.exe -m src.analysis.dataset_profile

# 2. Quick smoke test (seconds)
./.venv/Scripts/python.exe -m src.experiments.run_experiment --scales 1000 --repeats 1 --n-queries 500

# 3. Full run — defaults to 1k / 10k / full dataset, all approaches, both engines
./.venv/Scripts/python.exe -m src.experiments.run_experiment

# Narrower runs while iterating
./.venv/Scripts/python.exe -m src.experiments.run_experiment --engines postgres --scales 1000 10000
```

The full run's largest scale point (826,843 records x 5,000 queries x 3 approaches x 2
engines x repeats) will take a while — start with `--repeats 1` to time it before
committing to the default of 3.

Results accumulate (append-only) in `results/raw_results.csv`. Delete that file to start
a fresh run.

## Generating report tables & figures

```
./.venv/Scripts/python.exe -m src.analysis.generate_report
```

Produces the five named deliverables from plan B.8, plus the derived values the
Discussion section is written around:

- `results/tables/table1_performance.md` — **Table 1**: latency/throughput/CPU/storage
  per approach x engine at the largest scale point.
- `results/tables/table2_recovery.md` — **Table 2**: recovery accuracy per approach x
  engine.
- `results/figures/fig1_latency_vs_scale.png` — **Fig. 1**: latency vs. dataset size,
  one line per approach, one panel per engine.
- `results/figures/fig2_recovery_accuracy.png` — **Fig. 2**: the headline security
  result — recovery accuracy by approach (bars = engine): A ≈ 100% (sanity check), B
  high (encrypted ≠ confidential), C markedly lower (the mitigation), consistent across
  both engines.
- `results/figures/fig3_tradeoff_scatter.png` — **Fig. 3**: security-performance
  trade-off scatter (x = latency overhead % vs. A, y = recovery accuracy), one point per
  approach x engine.
- `results/tables/derived_values.md` — latency overhead of B/C vs. A per engine,
  storage-expansion factor, the B→C accuracy drop in percentage points (headline
  number), the cross-engine range of Approach-B accuracy, engines ranked by Approach-C
  overhead, and run-to-run variance/approx. 95% CI across repeats.
- `results/tables/summary.md` / `summary.csv` — full per-scale, per-metric summary if
  you need more than the five named deliverables.
- `results/figures/storage_expansion.png` — bonus chart, not a named B.8 deliverable.

## Notes for the report (things worth stating explicitly, per plan B.13)

- **CPU%** is measured as host-wide utilisation during the workload replay (`psutil`),
  not per-container — a documented limitation without per-container cgroup accounting.
- **Cross-engine performance numbers are not directly comparable** — report them as
  relative overhead against each engine's own Approach-A baseline (`derived_values.md`
  already does this).
- **Approach C only implements volume-hiding padding**, not additional frequency
  smoothing — state this as the specific mitigation being evaluated, not "all possible
  leakage reduction." Note also that its storage-expansion factor is scale-dependent:
  at very small scale points the fixed padding-bucket size (`PAD_BUCKET_SIZE=50`) is
  large relative to per-value group sizes, so the expansion factor is markedly higher at
  1k/10k than at full scale — expected behaviour, worth stating rather than treating as
  an anomaly.
- **The count attack's auxiliary knowledge is the dataset's own empirical distribution**
  of `specific_diagnostic_test` — modelled in the report as analogous to published
  hospital lab-utilisation statistics (see `dataset_profile.md` §6 for the full framing).
- **Approach-B recovery accuracy is not saturated at 100% at small scale points** — with
  297 candidate values and many singleton/near-singleton true counts, the count attack's
  frequency-matching can't perfectly disambiguate ties at 1k/10k; accuracy rises at the
  full-dataset scale point where counts separate more cleanly. This is a genuine,
  reportable finding about attack effectiveness vs. data scale, not a bug.
