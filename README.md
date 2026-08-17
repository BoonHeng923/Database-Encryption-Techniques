# Database-Encryption-Techniques — NoSQL leakage benchmark

Implements plan section B (Beyond Confidentiality benchmark): stores the same data four
ways — **A** plaintext, **B** deterministic/property-preserving encryption (leaks), **C**
deterministic encryption + naive (independently-sampled) decoy records, **D** deterministic
encryption + generatively-produced (co-occurrence-preserving) decoy records, a secret
HMAC-keyed real/decoy identification function, per-collection encryption keys, and name
tokenisation — in **MongoDB**, replays one identical query workload against every
combination, runs two leakage-abuse attacks (single-collection value recovery and
cross-collection linkage recovery) against each, and reports security and performance side
by side, before vs. after the solution.

No SQL engine is used — this is a NoSQL-only benchmark.

## Project layout

```
src/core/            shared, engine-independent pipeline
  config.py           env-driven configuration
  dataset.py           dataset loader + seeded sub-sampling (1k / 10k / full)
  schema.py             builds the 3 linked collections (patients/lab_orders/billing)
  encryption.py         AES-SIV deterministic tokens (global + per-collection keys) + AES-GCM payload encryption + name tokenisation
  secret_id.py           the B.4.1 secret real/decoy id(i)/isDecoy(i) formula
  decoys.py               decoy targeting, naive (C) and conditional (D) generators, the realism filter
  records.py               turns a dataframe into per-approach, per-collection stored rows (incl. decoys)
  workload.py           seeded, skewed query workload generator (per collection/schema)
  attack.py               value-recovery (count) attack + realism filter + cross-collection linkage attack
  metrics.py                result-row schema / CSV writer
  adapters/
    base.py                collection-aware StorageAdapter interface
    mongo_adapter.py         MongoDB implementation
src/experiments/run_experiment.py   orchestrates the scale x schema x approach x repeat grid
src/analysis/
  dataset_profile.py    B.5.1 dataset sanity check (run this first)
  generate_report.py    turns results/raw_results.csv into the B.8 tables/figures
data/raw/              adult_inpatient_patient_portal_data.xlsx (the real dataset)
data/processed/        dataset_cache.csv (fast-reload cache), per-scale/collection workload files
results/                raw_results.csv, tables/*.md, figures/*.png
docker-compose.yml      MongoDB container (+ optional app container)
```

## The four approaches

| Approach | What is stored | Purpose |
|---|---|---|
| A — Plaintext | Sensitive field in the clear | Baseline / attack sanity check (~100% recovery) |
| B — Deterministic | Value encrypted with one global key; same value -> same token everywhere | Common "encrypted database" practice: leaks frequency, volume, and cross-collection linkage |
| C — Naive decoys | B + independently-sampled fake records to flatten frequency | Shows decoys help but are filterable by a realism-checking attacker |
| D — Generative decoys (ours) | B + co-occurrence-preserving fake records + secret real/decoy id function + per-collection keys + name tokenisation | The contribution: resists the realism filter and breaks cross-collection linkage |

## The three-collection schema

`patients` (one row/patient: `patient_code`, `race_category`, `age_category`),
`lab_orders` (one row/test event: `patient_code`, `specific_diagnostic_test`,
`diagnostic_test_category`), `billing` (one row/test event: `patient_code`, a derived
`cost`/`cost_category`), all linked by `patient_code`. **Single-collection mode** uses
`lab_orders` alone (the original flat-table setting). Both modes are run by default
(`--schema both`).

## The two attacks

1. **Value recovery** (`attack.run_count_attack`) — the classic count/frequency-matching
   attack against the sensitive field per collection. For C/D, a **realism filter** is
   applied first (B.7 point 1) and both the filtered and unfiltered accuracy are reported.
2. **Linkage recovery** (`attack.run_linkage_attack`) — cross-collection: does the attacker
   correctly cluster the same patient's records across `patients`/`lab_orders`/`billing`
   by matching `patient_code` tokens? B/C share one key -> near-100% linkage; D uses a
   distinct key per collection -> linkage recovery collapses.

## Database: Dockerized

| Service | Container port(s) | Host port(s) | Credentials |
|---|---|---|---|
| `encbench_mongo` | 27017 | **27018** | `encbench_user` / `encbench_pass`, db `encbench` |

Bring it up:
```
docker compose up -d mongo
docker compose ps          # should show "healthy"
```

To stop: `docker compose down` (add `-v` only if you also want to delete the stored data
volumes — don't do this if you have results you still need reproduced).

Running the whole pipeline inside Docker too: `docker-compose.yml` defines an `app`
service — `docker compose run --rm app python -m src.experiments.run_experiment`.

## Dataset

The real dataset is in place: `data/raw/adult_inpatient_patient_portal_data.xlsx`
(826,843 de-identified inpatient diagnostic-test records). First load parses the Excel
file once (~70s) and caches it as `data/processed/dataset_cache.csv` for fast reloads
after that — delete the cache file if you ever replace the source `.xlsx`.

**Sensitive/attack-target field: `specific_diagnostic_test`** (297 distinct test names).
This was chosen over the other categorical fields in the file via the required B.5.1
sanity check — see below. It is the queried field for `lab_orders`; `patients` and
`billing` each get their own queryable field (`race_category`, `cost_category`) so the
value-recovery attack has something to target in multi-collection mode too.

If the `.xlsx` file is ever missing, the pipeline falls back to a small synthetic
generator with the same schema so it stays runnable, but say so explicitly if any
numbers in your report came from the fallback (`dataset_source` column in
`results/raw_results.csv` records which one was used for every row).

### Run the dataset sanity check first (plan B.5.1 — required gate)

```
./.venv/Scripts/python.exe -m src.analysis.dataset_profile
```

## Python environment

```
python -m venv .venv                      # already done
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # already done
```

Use `./.venv/Scripts/python.exe` for every command below.

## Keys

`.env` needs `ENC_MASTER_KEY_B64` (value encryption) and `DECOY_KEY_B64` (the B.4.1
real/decoy id function — deliberately a *separate* secret) before your final run:

```
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Paste one output into each of `ENC_MASTER_KEY_B64` and `DECOY_KEY_B64` in `.env`. Blank
values fall back to fixed demo keys (`config.py`) — fine for development, not for results
going into the report.

## Running the benchmark

```
# 1. Sanity check (once)
./.venv/Scripts/python.exe -m src.analysis.dataset_profile

# 2. Smoke test first (fast, isolates pipeline issues before committing to a long run)
./.venv/Scripts/python.exe -m src.experiments.run_experiment --approaches A B C D --schema both --scales 1000 --repeats 1 --n-queries 200

# 3. Full run — defaults to 1k / 10k / 30k, all approaches (A/B/C/D), both schemas
./.venv/Scripts/python.exe -m src.experiments.run_experiment
```

Results accumulate (append-only) in `results/raw_results.csv`. Delete that file to start
a fresh run.

## Generating report tables & figures

```
./.venv/Scripts/python.exe -m src.analysis.generate_report
```

Produces, per plan B.8:

- `results/tables/table1_performance.md` — **Table 1**: latency/throughput/CPU/storage
  per approach (single-collection schema, largest scale point).
- `results/tables/table2_recovery.md` — **Table 2**: value-recovery accuracy per
  approach.
- `results/tables/table3_linkage.md` — **Table 3**: cross-collection linkage-recovery
  accuracy, before (B) vs. after (D).
- `results/figures/fig1_latency_vs_scale.png` — **Fig. 1**: latency vs. dataset size.
- `results/figures/fig2_recovery_accuracy.png` — **Fig. 2**: the headline security
  result — B->C->D reduction, C/D shown post-realism-filter.
- `results/figures/fig3_tradeoff_scatter.png` — **Fig. 3**: security-performance
  trade-off scatter.
- `results/figures/fig4_data_view.png` — **Fig. 4**: before/after data view — one
  example record as A / B / D side by side.
- `results/figures/fig5_metadata_view.png` — **Fig. 5**: before/after metadata view —
  frequency histogram, linkage-token diagram, name-tokenisation example.
- `results/tables/derived_values.md` — latency/storage overhead vs. A, the B->D and
  C->D accuracy drops (headline numbers), run-to-run variance.
- `results/figures/storage_expansion.png` — bonus chart, not a named B.8 deliverable.

## Notes for the report (plan B.13/B.14)

- **CPU%** is host-wide (`psutil`), not per-container — a documented limitation.
- **Performance numbers are relative, not absolute** — report them as overhead against
  the Approach-A baseline rather than as machine-independent figures.
- **The value-recovery attack's auxiliary knowledge** is each collection's own empirical
  value distribution, standard for this line of attacks.
- **D's decoy targeting is expected, not exact** — `d` in the B.4.1 formula sets an
  *expected* decoy ratio (HMAC-driven, not deterministic count), so observed decoy counts
  fluctuate around the target; state this as intended behaviour.
