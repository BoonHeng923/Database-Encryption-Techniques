# SEG2102 — Implementation Details (as-built)

**Companion to:** `SEG2102_Introduction_and_Implementation_Plan.md` (Part B, now updated
for the MongoDB-only scope) and `SEG2102_MongoDB_Only_Plan.md` (Revision 3, the current
authoritative plan for what the Results section reports). Where this implementation
deviates from either plan, the deviation and its reason are called out explicitly rather
than silently.

> **How to use this file.** It is written to feed the **Methodology (Section 3, 6 marks)**
> and **Results (Section 5, 10 marks)** sections directly: architecture and module
> descriptions belong in Methodology; the "bugs found during verification" and "known
> limitations" sections belong in Methodology's validation subsection and/or Section 5's
> discussion, since they are genuine findings about the evaluation, not just cleanup notes.

---

## 1. What is actually running

**MongoDB only, Dockerized.** The pipeline was originally built and verified across three
NoSQL engines (MongoDB, Couchbase, Cassandra), plus an experimental ArangoDB adapter added
partway through — but multi-engine collection proved too slow to complete reliably within
the project timeline, and each of the other three engines surfaced its own real,
diagnosed-but-not-worth-fixing-further performance characteristic (see §7). **The study
was therefore run to completion in MongoDB only**, which has complete, clean data across
all three scale points and the full decoy-ratio sweep. The other three adapters and their
docker-compose services remain in the repository, unused by default — the client/adapter
split makes the pipeline engine-agnostic by design, so bringing any of them back is a
config change (`config.DEFAULT_ENGINES`), not a redesign.

**Four approaches, one shared pipeline.** A (plaintext) / B (deterministic encryption,
leaks) / C (deterministic + *naive* decoys) / D (deterministic + *generative* decoys +
secret real/decoy id function + per-collection keys + name tokenisation). All four are
produced by one function, `records.prepare_records()`, so every approach transforms the
exact same input data the exact same way.

**Two schema modes.** `single` = `lab_orders` alone (the original single-collection
design). `multi` = `patients` + `lab_orders` + `billing`, linked by `patient_code`,
enabling the cross-collection linkage attack.

**Two attacks.** Value-recovery (count/frequency-matching, with an attacker-side realism
filter for C/D) and cross-collection linkage-recovery (token-equality matching on
`patient_code` across collections).

**`decoy_target_ratio` is a first-class swept independent variable**, not a tuned
constant: `{0.5, 0.75, 1.0}`, run for both C and D, on both schema modes, at all three
scale points. This produced the study's strongest finding (§6, §8).

---

## 2. Docker setup

```
services: mongo | couchbase | cassandra | arangodb | app (optional, runs the pipeline in-container)
```

| Service | Image | Host port(s) | Status | Notes |
|---|---|---|---|---|
| `mongo` | `mongo:7` | 27018→27017 | **running, active** | Remapped so it coexists with a native Mongo install |
| `couchbase` | `couchbase:community-7.6.2` | 8091-8096, 11210 | stopped, descoped | Lazy cluster/bucket/index-storage-mode init in `CouchbaseAdapter` |
| `cassandra` | `cassandra:5` | 9042 | stopped, descoped | Lazy keyspace init in `CassandraAdapter` |
| `arangodb` | `arangodb:3.12` | 8529 | stopped, descoped | Added and verified functionally correct, then descoped for a fixed per-query latency floor (§7) |
| `app` | built from `Dockerfile` | — | optional | Runs `run_experiment` inside the Docker network instead of from the host |

**Only Mongo needs to be up for the current default configuration:**
```
docker compose up -d mongo
docker compose ps      # should show healthy
```
The other three can be brought back with `docker compose up -d couchbase cassandra
arangodb` and `--engines <name>` on the CLI if you want to revisit the multi-engine
appendix — their code and lazy self-healing init are unchanged and were last verified
working (Couchbase and Cassandra fully, ArangoDB functionally-but-slowly, all three
individually, see §7).

---

## 3. Core pipeline (`src/core/`) — engine-agnostic, shared by every adapter

### `config.py`
Environment-driven settings (`.env` / `.env.example`). Connection info for all four
engines (three of them unused by default); two **independent** 32-byte keys —
`ENC_MASTER_KEY_B64` (encrypts data) and `DECOY_KEY_B64` (drives the secret real/decoy id
function) — deliberately separate so compromising one doesn't compromise the other;
`DEFAULT_ENGINES = ["mongo"]`; `DEFAULT_APPROACHES = [A, B, C, D]`; `COLLECTIONS`/
`LINK_FIELD` for the 3-collection schema; `SENSITIVE_FIELD = specific_diagnostic_test`
(the B.5.1-vetted attack field); `SCALE_POINTS = [1_000, 10_000, 30_000]` (the third
scale point is a fixed value now, not the dynamically-resolved full dataset — a deliberate
scoping choice once the full-dataset point proved impractically slow across multiple
engines/repeats; `dataset.full_dataset_size()` still exists and is still used by the
B.5.1 sanity-check script, which profiles the true full dataset regardless);
`DECOY_TARGET_RATIO` (default single/"canonical" value, 0.5, used where exactly one value
is needed) and `DECOY_TARGET_RATIOS = [0.5, 0.75, 1.0]` (the swept range — see §6).

### `dataset.py`
Loads/caches the raw Excel file (826,843 records), falls back to a synthetic generator if
the file is missing, and provides seeded sub-sampling to the current scale points.

### `schema.py`
Splits the flat dataset into the three linked collections:
- `patients` — one row per patient (`patient_code`, `race_category`, `age_category`)
- `lab_orders` — one row per test event (`patient_code`, `specific_diagnostic_test`,
  `diagnostic_test_category`) — carries the vetted sensitive field
- `billing` — one row per test event (`patient_code`, `diagnostic_test_category`, a
  derived `cost` and `cost_category`)

`cost_category` is bucketed with **fixed dollar thresholds** (`pd.cut`, tiers
`tier_low`/`tier_mid`/`tier_high`/`tier_premium`), not quantile bins — see §7, bug 4, for
why that fix mattered.

`QUERY_FIELD`/`COMPANION_FIELDS` per collection define what each collection's supplementary
value-recovery attack targets and which fields the decoy generators use for realism.

### `encryption.py`
AES-SIV deterministic tokens (equality-queryable) and AES-GCM payload encryption. Adds
`derive_token_key(collection: str | None)`: `None` → one global key shared across all
collections (used by B and C — this is *why* they leak cross-collection linkage);
`"patients"|"lab_orders"|"billing"` → a distinct HKDF-derived key per collection (used by
D — this is what breaks the linkage).

### `secret_id.py` — the B.4.1 "formula"
```
id(i)      = HMAC_SHA256(k, "id"  || i)
isDecoy(i) = 1  if  HMAC_SHA256(k, "tag" || i) mod (d+1) == 0   else 0
```
`k` never leaves the client. `iter_ids(n_real, n_decoy, ...)` walks the counter, emitting
real or decoy entries until **both** quotas are met, deriving `d` (and, when decoys
outnumber reals, inverting which HMAC outcome counts as "decoy") so the true decoy
fraction is represented accurately in both directions — see §7, bug 5.

### `decoys.py`
- `compute_target_counts(value_counts, target_ratio)` — the *targeting* policy: pad every
  value's count up toward `target_ratio × max(count)`. Shared by C and D so only *realism*
  differs between them.
- `naive_decoy_generator` (C) — samples each companion field **independently** from its own
  marginal. Cheap, but produces field combinations that rarely co-occur in real data.
- `conditional_decoy_generator` (D) — samples companion fields **jointly**, conditioned on
  the target value, from the real data's own conditional distribution. A lightweight
  conditional sampler, not a full CTGAN/GAN — an explicitly permitted simplification (plan
  B.4.2/B.9).
- `realism_filter` — the attacker-side check: flags a record's field combination as
  implausible if its empirical joint probability is near zero.

### `records.py` — `prepare_records(df, approach, collection, sensitive_field, decoy_target_ratio)`
The single function every adapter calls. A: plaintext passthrough. B: deterministic
tokens, shared key. C/D: B plus decoys (naive or conditional), with server-visible ids
minted from `secret_id.iter_ids` so real and decoy records are indistinguishable on the
server; D additionally uses per-collection keys for the sensitive field and `patient_code`.

### `attack.py`
- `run_count_attack` — the value-recovery attack: matches observed (token, volume) pairs to
  the true value-frequency distribution via optimal (Hungarian/`linear_sum_assignment`)
  assignment. Token order is **seed-shuffled before matching** — see §7, bug 6, this was a
  real bug, not a style choice.
- `apply_realism_filter` / `build_realism_keep_map` — reruns the attack after the attacker
  discards records that fail `decoys.realism_filter`.
- `run_linkage_attack` — cross-collection: groups records by `patient_code`, treats
  matching `patient_token` bytes as a claimed link, scores against ground truth.

### `workload.py`, `metrics.py`
Seeded, frequency-proportional query generation (cached per scale+collection+schema
label); the `ResultRow` schema written to `results/raw_results.csv` (includes `schema`,
`collection`, `recovery_accuracy_filtered`, `linkage_recovery_accuracy`,
`decoy_target_ratio`).

---

## 4. Storage adapters (`src/core/adapters/`)

One `StorageAdapter` interface (`setup`, `bulk_load`, `query_equality`,
`storage_size_mb`, `close`), all collection-aware (`{approach}_{collection}` is the
addressing scheme everywhere). Only `mongo_adapter.py` is on the active path; the other
three are kept for the optional appendix.

| Adapter | Status | Indexing | Storage measurement |
|---|---|---|---|
| `mongo_adapter.py` | **active** | Index on `token`/`sensitive_value` per collection | `collStats` |
| `couchbase_adapter.py` | descoped | N1QL secondary index per collection (scope=collection, Couchbase-collection=approach) | Bucket-level REST stats (not exact per-approach) |
| `cassandra_adapter.py` | descoped | CQL secondary index on `token_val` (`token` is a reserved word) | Approximate: row count × sampled average row size (`nodetool` isn't reachable from the app process) |
| `arango_adapter.py` | descoped | Persistent index per collection, via AQL cursor | `db.collection().statistics()` |

`config.py`'s `run_experiment.py --engines` CLI still accepts `mongo couchbase cassandra
arangodb`; only the default list changed.

---

## 5. Experiment runner and report generation

`run_experiment.py` grid: **scale × engine × schema × approach × (decoy ratio, C/D only) ×
repeat**. CLI: `--scales`, `--engines {mongo,couchbase,cassandra,arangodb}`, `--approaches
{A,B,C,D}`, `--schema {single,multi,both}`, `--repeats`, `--n-queries`, `--decoy-ratios`.
A/B run once per (scale, engine, schema); C/D additionally sweep `--decoy-ratios`. The
linkage attack runs once per (scale, engine, schema, approach) after all collections/ratios
for that approach are loaded (linkage doesn't depend on the ratio).

**Two report generators exist.** `generate_report.py` is the original, general-purpose,
multi-engine report builder (still fully functional — filters to `config.DEFAULT_ENGINES`,
so currently produces Mongo-only output too). `generate_mongo_report.py` is the **current
primary path**, purpose-built to produce exactly `SEG2102_MongoDB_Only_Plan.md`
Revision 3's deliverables from the same `raw_results.csv`, no new experiment runs needed:

| Output | Content |
|---|---|
| Table 1 (`table1_before_after_performance.md`) | A → B → D latency/throughput/CPU on `lab_orders`, all 3 scale points (D shown at ratio=1.0, the operating point that actually works) |
| Table 2 (`table2_recovery_vs_ratio.md`) | Value-recovery vs. `decoy_target_ratio` — **the cliff** |
| Table 3 (`table3_linkage_before_after.md`) | Linkage recovery, before (A/B/C) vs. after (D), all 3 scales |
| Table 4 (`table4_cost_vs_ratio.md`) | Storage-expansion factor vs. ratio, `lab_orders` + `patients` |
| `billing_supplementary.md` | `billing`/`cost_category`, explicitly non-headline (§9) |
| `mongo_derived_values.md` | Overhead %, B→D drop per ratio, cliff bound, C-vs-D filter gap, expansion cost of the cliff, cross-scale consistency |
| Fig. 1 | Performance before/after (A/B/D line plot, log-scale x) |
| Fig. 2 | **The cliff** — recovery vs. ratio, B/C-filtered/D-filtered lines — headline figure |
| Fig. 3 | Security-cost trade-off scatter (expansion × vs. recovery %, one point per approach×ratio) |
| Fig. 4 | Linkage before/after, grouped by scale (scale-independence) |
| Fig. 5 | Before/after **data** view — reused from `generate_report.py`'s `plot_fig4_data_view` (row-aligned A/B/D record comparison with leak/protected badges), copied under this plan's Fig. 5 name |
| Fig. 6 | Before/after **metadata** view — (a) frequency histogram at ratio 0.5 vs. 1.0, (b) cross-collection linkage-token diagram |

Run with:
```
./.venv/Scripts/python.exe -m src.analysis.generate_mongo_report
```

The old `generate_report.py` outputs that this superseded (old Table 1/2/3, the old
`table_ratio_sweep.md`, old Figs 1/2/3/6, `storage_expansion.png`) were deleted from
`results/` as redundant; re-running `generate_report.py` would recreate them since its
code is untouched. `table2b_percollection_diagnostics.md`, the old `derived_values.md`
(has run-to-run variance stats the new file doesn't), and `summary.md`/`.csv` were kept —
they're still uniquely useful, not superseded.

---

## 6. `decoy_target_ratio`: the cliff, not a slope

Recovery does **not** fall gradually as the ratio rises from 0.5 to 1.0 — it stays roughly
flat through 0.5–0.75 and **collapses sharply only at full flattening (ratio = 1.0)**. This
is the single strongest result in the study. Confirmed on MongoDB, `lab_orders`, scale =
30,000 (the headline scale — pattern holds at 1k/10k too):

| ratio | B | C (unfiltered / filtered) | D (unfiltered / filtered) |
|---|---|---|---|
| 0.5 | 93.3% | 39.6% / 39.7% | 39.6% / 39.6% |
| 0.75 | 93.3% | 32.4% / 39.6% | 32.4% / 32.4% |
| **1.0** | 93.3% | **0.0% / 22.2%** | **0.0% / 0.0%** |

At the cliff, the C-vs-D contrast is exactly the hypothesis: naive decoys (C) are still
~22% recoverable once the attacker's realism filter strips the implausible ones out;
generative decoys (D) stay at 0% even under the filter. **This 22.2-percentage-point gap
is the headline contribution number.**

That protection isn't free: storage expansion on `lab_orders` rises from 41.1× (ratio 0.5)
to 89.4× (ratio 1.0) for D — a 2.18× storage multiple to go from partial to near-total
protection. Table 4 / Fig. 3 report the full curve, not a single point.

---

## 7. Bugs found and fixed during verification

Each of these would have produced misleading numbers if left in place, and each was caught
by actually running the pipeline end-to-end rather than trusting the code in isolation —
worth stating explicitly in Methodology's validation subsection.

1. **Couchbase: missing index storage mode.** A freshly `cluster-init`'d Couchbase node
   has the index service enabled but no storage mode selected; every `CREATE INDEX` failed
   silently, so zero indexes ever existed and every query fell back to a full collection
   scan — a uniform ~150–250ms per query, a 30–100× gap versus MongoDB that looked like an
   inherent Couchbase weakness but was one missing REST call
   (`POST /settings/indexes {storageMode: forestdb}`). Fixed in
   `CouchbaseAdapter._ensure_index_storage_mode()`; latency dropped to ~3–14ms.

2. **Couchbase: GSI eventual-consistency race.** Queries issued immediately after bulk
   loading undercounted results. Fixed by polling the index-driven count to convergence at
   the end of `bulk_load()` before any query is timed.

3. **Cassandra driver on Python 3.12/Windows.** Needed `gevent` +
   `gevent.monkey.patch_all()` (the driver's default connection class needs `asyncore`,
   removed in 3.12). `token` is a reserved CQL keyword, renamed to `token_val`.

4. **`billing`'s `cost_category` was uniform by construction.** `pd.qcut` produces
   equal-count bins *by definition*, so the field had zero real skew — B, C, D were
   structurally identical on it regardless of decoy generation. Replaced with fixed dollar
   thresholds (`pd.cut`), letting the real per-test-frequency skew show through; billing
   now shows genuine movement (100%→46.5%) instead of a flat artifact.

5. **`secret_id.py` under-produced decoys for heavily-skewed minority values.** The
   id-generation loop stopped once the real-record quota was met; when a value needed far
   more decoys than reals, the loop exhausted its real quota long before enough decoys were
   emitted. Reworked to track both quotas and derive the HMAC-modulus parameter (and which
   outcome represents "decoy") from whichever class is rarer.

6. **`attack.py`'s tie-breaking leaked information the attacker doesn't actually have.**
   When decoys fully flatten observed volumes to an exact tie, the Hungarian assignment
   still resolves deterministically by row/column index, and because query tokens are
   inserted in the order queries are drawn (correlated with true frequency), the
   "arbitrary" tie-break was silently aligned with the correct answer — full flattening
   still showed ~97% recovery on `patients` even though every candidate's observed volume
   was provably identical. Fixed with a seeded shuffle of token order before assignment.
   *(Bugs 5 and 6 compounded — fixing only one would not have produced the correct result;
   both were necessary, and finding them required running the full pipeline against real,
   skewed data, not unit-testing each function in isolation.)*

7. **Cassandra's secondary index scales poorly for low-selectivity queries.** At scale
   10,000, `patients`' dominant `race_category` value (`White`, ~81% of rows) returns most
   of the table for a single equality query. Mongo's latency for that query grew ~3× from
   scale 1,000→10,000 (4.3ms→12.9ms — expected, more matched rows means more data to
   transfer); Cassandra's grew ~8.4× (6.6ms→55.6ms). Verified via `nodetool` that this
   wasn't resource starvation or a stuck process — a real, reportable Cassandra
   characteristic for this workload shape, not a configuration bug. Contributed to the
   decision to descope Cassandra from the active engine list.

8. **ArangoDB: a fixed ~43ms floor per query, independent of complexity.** Diagnosed via
   raw HTTP requests to isolate the cause: `RETURN 1` (zero data access, zero indexing)
   still cost ~43ms through `/_api/cursor` (the AQL endpoint — `collection.find()` also
   routes through it in this ArangoDB version, so there was no lighter-weight escape
   hatch), while every non-AQL endpoint (`/_api/version`, `/_api/collection`) cost ~1.4ms.
   This is AQL's own query-engine/transaction setup cost in this environment, not a missing
   index or a driver bug. At that floor, the standard 5,000-query workload would take
   multi-hour runs across the full grid; ArangoDB was descoped after confirming it was
   otherwise functionally correct (indexes used properly, correct A=100%/B=72.4% recovery).

9. **`ciphertext_expansion_factor` silently defaulted to 1.0× for chunked runs.**
   `run_experiment.py` computed expansion as `storage_mb / baseline_storage[A]`, where the
   A-baseline was only captured if approach A ran *within the same process invocation*.
   Several multi-schema D/C runs at scale 30,000 were split into separate background jobs
   (`--approaches D` only, etc.) to survive interruptions, and those jobs never saw
   approach A — so the column silently logged `1.0` instead of the real expansion factor
   for those rows, and it would have gone unnoticed if Table 4 had been built by trusting
   the stored column. Fixed two ways: `run_experiment.py` now falls back to querying A's
   actual storage directly (A's collection persists across runs; `setup()` only drops the
   collection currently being processed) when a chunked run never touched it; and
   `generate_mongo_report.py`'s Table 4 recomputes expansion from each row's actual
   `storage_mb` against the collection's own A-baseline row rather than trusting the
   column at all, so old corrupted rows in `raw_results.csv` don't silently propagate into
   the report either.

---

## 8. Verified results (headline, MongoDB, all three scale points)

Single-collection (`lab_orders`/`specific_diagnostic_test`), the cliff (§6) — see Table 2
above for the full ratio × approach breakdown at scale=30,000; the same qualitative
pattern (flat 0.5→0.75, collapse at 1.0) was confirmed at 1,000 and 10,000 as well.

Linkage (multi-schema, `patient_code`), all three scales:

| scale | A | B | C | D |
|---|---|---|---|---|
| 1,000 | 100% | 100% | 100% | **0%** |
| 10,000 | 100% | 100% | 100% | **0%** |
| 30,000 | 100% | 100% | 100% | **0%** |

Stable at 100%/100%/100%/0% across every scale point tested — the linkage defence is
scale-independent.

Performance before/after (A → B → D at ratio=1.0, `lab_orders`):

| scale | A (ms) | B (ms, overhead) | D (ms, overhead) |
|---|---|---|---|
| 1,000 | 1.550 | 1.556 (+0.4%) | 3.292 (+112.3%) |
| 10,000 | 3.294 | 3.311 (+0.5%) | 5.032 (+52.8%) |
| 30,000 | 6.486 | 6.678 (+3.0%) | 14.233 (+119.4%) |

---

## 9. Known limitations (state plainly)

- **Cross-engine generalisation is only partially verified.** MongoDB is the fully
  evaluated engine. Couchbase and Cassandra were both verified individually to reproduce
  the cliff and linkage=0% pattern at earlier points in development (before the ratio
  sweep and the tie-breaking/decoy-generation fixes in §7 landed), and ArangoDB was
  verified functionally correct but not performance-viable. None of the three has a
  complete, current, full-grid re-run under the final code — if the optional appendix is
  written up, say explicitly which fixes predate/postdate whatever data is cited.
- **`patients`/`billing`'s own value-recovery numbers are supplementary, not headline.**
  `race_category` (5 values, one at 81%) and `cost_category` (4 tiers, now genuinely
  skewed post-fix) are both lower-cardinality than the B.5.1-vetted
  `specific_diagnostic_test`; their recovery floor is structurally higher, which is itself
  a documented, expected finding, not a defect.
- **The conditional sampler is not a full GAN.** State this plainly rather than
  overclaiming "generative model" — it is the plan's own explicitly-permitted lightweight
  alternative (B.4.2/B.9).
- **The cliff's exact threshold is bounded, not pinpointed**: D's filtered recovery is
  32.4% at ratio=0.75 and 0.0% at ratio=1.0, so the cliff falls somewhere in (0.75, 1.0] —
  narrowing it further (e.g. ratio=0.85/0.90/0.95) is listed as optional future work in
  `SEG2102_MongoDB_Only_Plan.md`, not yet run.
- **Some multi-schema scale=30,000 combinations have fewer repeats than the rest of the
  grid** (1 instead of 3), from the background-job chunking used to survive interruptions
  during that run — the values themselves are correct (single-run measurements, not
  corrupted), just without the same run-to-run variance data as the fully-repeated cells.

---

## 10. How to reproduce

```
docker compose up -d mongo

./.venv/Scripts/python.exe -m src.experiments.run_experiment --scales 1000 10000 --repeats 1   # timed trial
./.venv/Scripts/python.exe -m src.experiments.run_experiment                                    # full grid (MongoDB only)
./.venv/Scripts/python.exe -m src.analysis.generate_mongo_report                                # current primary report path
./.venv/Scripts/python.exe -m pytest tests/                                                     # regression check
```

To bring another engine back into the grid:
```
docker compose up -d couchbase cassandra arangodb
./.venv/Scripts/python.exe -m src.experiments.run_experiment --engines couchbase cassandra arangodb ...
./.venv/Scripts/python.exe -m src.analysis.generate_report   # multi-engine-capable generator
```
