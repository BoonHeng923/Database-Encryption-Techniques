# SEG2102 — Introduction & Implementation Plan

**Working title:** *Beyond Confidentiality: Quantifying Access-Pattern and Volume Leakage in Encrypted SQL and NoSQL Databases under a Common Benchmark*

> **How to use this file.** Part A is the draft **Introduction (Section 2, worth 3 marks)** written to the marking rubric — paste it into your IEEE Word report and adjust citation numbers to match your group's shared reference list. Part B is a **detailed implementation plan** that turns your chosen domain gap (#1, leakage) plus the methodological "common-benchmark" gap into one **engine-agnostic pipeline you can build, run, and measure across six database engines (three SQL: PostgreSQL, MySQL, MariaDB; three NoSQL: MongoDB, Couchbase, Cassandra)** — satisfying the mandatory NoSQL requirement while proving the pipeline generalises across engines and both database families, so it feeds the Methodology (6 marks) and Results (10 marks) sections.
>
> **Citation placeholders:** references are written as `[X1]`, `[X2]`… where they are *new* sources the Introduction needs, and as `[LR-n]` where they should reuse a paper already in your literature review (e.g., Cao 2023, Gui 2023). Renumber everything into one IEEE sequence at the end.

---

## Part A — Introduction (Section 2)

The rubric breaks the 3 marks into three graded elements, each needing supporting references: **(i) overview of prior literature with connections to prior work**, **(ii) a problem statement that gives decision-useful insight**, and **(iii) measurable/testable objectives**. The draft below is organised so each element is unmistakable to the marker, mirroring the lettered-subsection style used in the lecturer's sample.

### 2. Introduction

#### General Background

Database Management Systems (DBMS) are the backbone of modern information infrastructure, responsible not only for storing and retrieving large volumes of data but also for enforcing data integrity, scalability, and access control [X1]. As organisations migrate sensitive workloads to cloud and outsourced environments, encryption has become the primary safeguard for confidentiality, ensuring that data remains unintelligible to any party without the decryption key even if the underlying storage is breached [LR-Mohamed]. This need spans both relational (SQL) systems and NoSQL databases such as MongoDB, the latter's document model and horizontal scalability having made it a default choice for large-scale, cloud-hosted applications that routinely handle personal and regulated data [X2]. To protect such data while still allowing it to be queried, a family of techniques known collectively as *encrypted search* — including searchable symmetric encryption (SSE), order-preserving/order-revealing encryption (OPE/ORE), and deterministic encryption — has been developed so that a server can execute queries directly over ciphertext without ever holding the plaintext, in both relational and document stores [LR-Ocenas], [X3].

#### Problem Statement

A widespread but dangerous assumption is that once data is encrypted, it is secure. In practice, the encrypted-search techniques that make querying possible do not achieve the semantic security of conventional encryption: they deliberately reveal auxiliary information — *access patterns* (which encrypted records a query touches), *search patterns* (whether two queries are identical), and *volume* (how many records a query returns) — so that the server can locate matching data efficiently [LR-Gui], [X3]. A growing body of *leakage-abuse* research has shown that an adversary who merely observes this leakage, without ever decrypting a single value, can reconstruct query contents and recover the underlying plaintext with high accuracy [LR-Gui], [X4]. Order-preserving schemes leak even more, as the ciphertext ordering exposes the distribution of the plaintext and enables inference attacks [LR-Cao]. The central problem is therefore twofold. First, **encrypted-query functionality is routinely treated as equivalent to confidentiality, when it is not** — a misconception with direct consequences for anyone making long-term decisions about how to protect regulated data in an outsourced DBMS. Second, **the leakage of competing schemes is reported under inconsistent datasets, query workloads, and threat models**, so a practitioner has no common basis on which to judge how much any given scheme actually leaks, or what it costs in performance to leak less [LR-Carvalho], [X4].

#### Significance of the Problem

This problem matters because the gap between *perceived* and *actual* security is exactly where real breaches occur. Regulations such as the GDPR and HIPAA treat encryption as a core safeguard for personal data [LR-Pina], yet an encrypted database that leaks access patterns can still expose which patients hold which diagnoses, or which customers transact with which partners, through inference alone — a disclosure that is invisible to conventional security testing and unaccounted for by compliance checklists [X4]. As encrypted NoSQL deployments scale into the cloud, the volume of observable query traffic grows, and with it the adversary's leverage for statistical inference [X2]. Providing decision-makers with a clear, measured picture of *what each encrypted-search approach leaks and what that protection costs* is thus essential for choosing defensible database designs, rather than relying on the false comfort that "the data is encrypted."

#### Objective

The objective of this report is to **design, implement, and evaluate a single controlled benchmark that quantifies the confidentiality–performance trade-off of encrypted-search techniques, and to show that it holds across multiple SQL and NoSQL database engines.** Concretely, the study will:

1. Implement a representative set of query-able encryption approaches — a baseline plaintext store, a deterministic/property-preserving scheme, and a leakage-reduced approach — as **one engine-agnostic pipeline** applied to the same dataset and workload across **six database engines (SQL: PostgreSQL, MySQL, MariaDB; NoSQL: MongoDB, Couchbase, Cassandra)**.
2. **Measure leakage quantitatively** by running a documented access-pattern / volume inference attack against each approach and reporting the adversary's query-recovery accuracy as a security metric.
3. **Measure the performance cost** of each approach under an identical workload using query latency, throughput, CPU utilisation, and storage/ciphertext expansion.
4. Produce a side-by-side comparison, under one common dataset, workload, and threat model, that makes the security-versus-performance trade-off explicit and reproducible, and **confirm that the leakage behaviour is consistent across all six SQL and NoSQL engines** while noting where performance overhead is engine-dependent.

These objectives are measurable and testable: each yields numeric metrics (recovery accuracy in %, latency in ms, throughput in ops/s, overhead in %) that can be compared against each engine's plaintext baseline and cross-checked against published benchmarks, supporting the conclusions drawn in Section 5.

#### Scope of the Report

This report focuses on **single-server, outsourced encrypted search** and the leakage that arises from querying encrypted data. To show that the problem and its mitigation are general rather than engine-specific, the study implements one common pipeline and evaluates it on **six database engines — three SQL (PostgreSQL, MySQL, MariaDB) and three NoSQL (MongoDB, Couchbase, Cassandra)**. It covers deterministic/property-preserving encryption and a leakage-reduced construction, evaluates them against a defined honest-but-curious adversary using a known inference attack, and reports both security (recovery accuracy) and performance metrics. It does **not** cover fully homomorphic encryption or trusted-execution-environment approaches (reviewed separately in the literature review as alternative computation-over-encrypted-data paradigms), network-level metadata leakage, secure multi-party computation, or multi-user key distribution, each of which is a distinct problem beyond the confidentiality-of-querying focus adopted here.

#### Use of High-Quality Sources

Every claim in this introduction is drawn from peer-reviewed journals and conference papers from reputable publishers (IEEE, ACM, Elsevier, Springer) and cited in IEEE format immediately after the relevant statement. Foundational and leakage-specific sources are shared with the literature review to maintain a cohesive evidentiary chain.

---

### New references the Introduction needs

Add these to your reference list (renumber into the shared IEEE sequence). Bracketed tags map to the placeholders above.

- `[X1]` — a recent DBMS-fundamentals or database-security survey (IEEE/Elsevier/Springer, ≤5 yrs) for the general-background sentence.
- `[X2]` — a NoSQL / MongoDB security or cloud-database paper establishing scale and sensitivity of NoSQL workloads.
- `[X3]` — a survey of encrypted search / searchable encryption (e.g., an SSE survey) defining access-pattern, search-pattern, and volume leakage. *Gui, Paterson & Patranabis, "Rethinking Searchable Symmetric Encryption," IEEE S&P 2023 fits well and may already be in your LR.*
- `[X4]` — a recent leakage-abuse attack paper quantifying query/plaintext recovery from access-pattern or volume leakage (e.g., a Sap/Jigsaw/IHOP-style USENIX or ACM CCS paper, 2021–2025).
- `[LR-Mohamed]`, `[LR-Ocenas]`, `[LR-Gui]`, `[LR-Cao]`, `[LR-Pina]`, `[LR-Carvalho]` — reuse the numbers these already have in your literature review.

---

## Part B — Detailed Implementation Plan

This plan operationalises **domain gap #1 (encrypted-query functionality leaks information and is not equivalent to confidentiality)** together with the **methodological gap (no common-workload, common-threat-model comparison)**. It is designed as a **single, engine-agnostic pipeline that runs across several SQL and NoSQL database engines**, satisfying the assignment's mandatory NoSQL requirement while also proving — in the Results section — that the same pipeline and findings hold regardless of engine. It is scoped so a three-person team can build and measure it, and it produces the quantitative results the 10-mark Results section needs.

**Engines under test.** The benchmark is run on **six database engines — three SQL and three NoSQL**:

| Family | Engines | Why included |
|---|---|---|
| **SQL (relational)** | **PostgreSQL** (primary), **MySQL**, **MariaDB** | PostgreSQL pairs with Pina [7] in the literature review; MySQL and MariaDB are the two engines your own literature review discusses (Carvalho, Natarajan), and MariaDB is a near-twin fork of MySQL, giving a natural control. All three share the SQL client protocol, so only the driver changes. |
| **NoSQL** | **MongoDB** (primary, mandatory), **Couchbase**, **Cassandra** | MongoDB is the required document store; Couchbase is a second document store with a SQL-like query language (N1QL/SQL++); Cassandra is a wide-column store, a genuinely different data model that strengthens the "works across NoSQL families" claim. |

Adding engines is cheap because of the architecture below: everything except a thin **storage adapter** is shared. Redis and other pure key-value stores are deliberately **excluded** and noted as a limitation, because Approach B requires an equality query over an encrypted *field*, which key-value stores do not support cleanly.

**Why the pipeline is engine-agnostic.** The quantity being measured — access-pattern, volume, and frequency leakage from *querying encrypted data* — is a property of the **encryption-and-query strategy, not the storage engine**. Every stage except one is shared across engines: the client-side encryption layer, the query encoder, the seeded workload driver, the adversary/attack module, and all metrics are identical. Only a thin **storage adapter** differs — for example `find({field: token})` on MongoDB versus `SELECT ... WHERE field = token` on the SQL engines versus the equivalent N1QL/CQL lookup on Couchbase/Cassandra — so "works across engines" is achieved by adding one small adapter per engine behind a single interface. Property-preserving encryption maps cleanly to every one of these models: a deterministic-encrypted document field or SQL column both support equality queries, and an order-preserving encoding supports range queries. This mirrors classic encrypted-relational-database systems (e.g., CryptDB) and the leakage-abuse literature, which was originally defined on SQL databases — so running the attack on *six* engines across two families is a strong demonstration that the leakage is intrinsic to the strategy, not an artefact of one engine.

### B.1 Core idea in one sentence

> Build the *same* dataset three ways — (A) plaintext baseline, (B) property-preserving/deterministic encryption that supports querying but leaks, and (C) a leakage-reduced scheme — **on six engines (SQL: PostgreSQL, MySQL, MariaDB; NoSQL: MongoDB, Couchbase, Cassandra)**, then run **one identical query workload** and **one identical inference attack** across all of them, reporting security (attacker recovery accuracy) and performance (latency/throughput/CPU/storage) on a common scale.

This directly demonstrates the thesis of your literature review: encrypted ≠ confidential, and the leakage/performance trade-off is only visible under a controlled comparison — and that the result holds across engines and across both database families.

### B.2 Research design

- **Type:** Quantitative, experimental **comparative study** (matches Methodology rubric 4.2).
- **Independent variables:** (1) encryption/search approach (A plaintext, B deterministic/OPE-style, C leakage-reduced); (2) **storage engine (6 levels: PostgreSQL, MySQL, MariaDB, MongoDB, Couchbase, Cassandra)**; (3) data scale.
- **Dependent variables:** (security) attacker query-recovery accuracy; (performance) mean query latency, throughput, CPU %, index+data storage size, ciphertext expansion.
- **Controlled/held constant:** dataset, seeded query workload, hardware/VM, engine versions, warm-up procedure, number of repetitions — held identical so approach, engine, and scale are the only things that vary.
- **Threat model:** honest-but-curious server/observer who sees the encrypted store, the encrypted queries, and the returned encrypted record sets (access pattern + volume), plus a realistic amount of auxiliary knowledge about the data distribution. This is the standard leakage-abuse setting and is identical for every engine.
- **Phasing (to keep the workload realistic).** The full grid is 3 approaches × 6 engines × 3 scale points × N repeats. To protect the timeline, run it in two phases: **Phase 1 (core, mandatory):** the two primary engines, **MongoDB** and **PostgreSQL**, across all approaches, scales, and repeats — this alone satisfies the assignment. **Phase 2 (extension):** the four additional engines (MySQL, MariaDB, Couchbase, Cassandra). If time is tight, Phase 2 may be run at the largest scale point only, or with fewer repeats, and this is stated openly as a scoping decision rather than a gap.

### B.3 System architecture

The trusted-client stages and the adversary are **shared and engine-independent**; only the boxed **storage adapter** is added once per engine.

```
   ┌──────────────────────────────────────────────────────────────────┐
   │                        Client (trusted)  — SHARED                  │
   │  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐  │
plaintext│ Encryption/   │─▶│ Query encoder │─▶│ Seeded workload driver │  │
dataset─▶│ bucketiser    │  │ (enc. query)  │  │ (replays same queries) │  │
   │  └──────────────┘  └───────────────┘  └───────────┬────────────┘  │
   └──────────────────────────────────────────────────┼───────────────┘
                                                       │ encrypted query + token
        ┌────────────┬────────────┬───────────────────┼──────────┬────────────┐
        ▼            ▼            ▼                     ▼          ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐          ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Adapter │ │ Adapter │ │ Adapter │          │ Adapter │ │ Adapter │ │ Adapter │
   │Postgres │ │ MySQL   │ │ MariaDB │          │ MongoDB │ │Couchbase│ │Cassandra│
   │ (SQL)   │ │ (SQL)   │ │ (SQL)   │          │ (doc)   │ │ (doc)   │ │(wide-col)│
   └────┬────┘ └────┬────┘ └────┬────┘          └────┬────┘ └────┬────┘ └────┬────┘
        └───────────┴───────────┴──────────┬─────────┴───────────┴──────────┘
                                           │ observed: access pattern, volume, search pattern
                                           ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │         Adversary module (leakage-abuse attack)  — SHARED          │
   │   input: observed leakage + aux. distribution                      │
   │   output: recovered query values, recovery accuracy %              │
   └──────────────────────────────────────────────────────────────────┘
```

Each `Adapter` is one small implementation of a single interface (`store()`, `query()`); everything above and below the adapter row is written once and reused for all six engines. *(Reuse this diagram in Methodology 4.5 "Flow Diagram or Architecture".)*

### B.4 The three approaches to implement

Each approach is applied **identically on every engine** (a collection/table holding the same records in each of the six databases).

| Approach | What it is | Query support | Expected leakage | Expected performance |
|---|---|---|---|---|
| **A — Plaintext baseline** | Unencrypted field (Mongo) / column (SQL) | Full/native | Everything (control) | Fastest; the reference point |
| **B — Deterministic / property-preserving** | Sensitive field/column encrypted so equality (deterministic) and/or range (OPE-style bucketed) queries still work; e.g., deterministic AES for equality, order-preserving encoding for ranges | Equality (+ range) | High: access pattern, volume, ordering/frequency | Small overhead; near-baseline latency |
| **C — Leakage-reduced** | Same queries but leakage deliberately suppressed: **volume-hiding via fixed-size bucket padding** and/or **frequency-smoothing** so equal-valued records are indistinguishable and result sizes are padded to a common size | Equality (bucketed) | Reduced: access pattern partly masked, volume hidden | Higher latency + storage from padding — the cost of confidentiality |

You do **not** need to invent new cryptography. Approach C can be a well-known, implementable mitigation such as **fixed-bucket volume-hiding / padding** and **deterministic-with-salted-buckets frequency smoothing** — both are standard, codeable in Python, and directly reduce the leakage the attack exploits. This keeps the project achievable while still demonstrating the trade-off.

**How each approach maps onto the engines** (only the storage adapter differs between engines; the encryption itself is shared client-side code):

| Engine | Family | Where ciphertext lives | Equality query (B/C) | Driver |
|---|---|---|---|---|
| PostgreSQL | SQL | `BYTEA` column | `SELECT ... WHERE field = token` | `psycopg2` |
| MySQL | SQL | `VARBINARY`/`BLOB` column | `SELECT ... WHERE field = token` | `mysql-connector-python` |
| MariaDB | SQL | `VARBINARY`/`BLOB` column | `SELECT ... WHERE field = token` | `mariadb` (or `mysql-connector`) |
| MongoDB | NoSQL (document) | field in a BSON document | `find({field: token})` | `pymongo` |
| Couchbase | NoSQL (document) | field in a JSON document | N1QL/SQL++ `SELECT ... WHERE field = token` | `couchbase` SDK |
| Cassandra | NoSQL (wide-column) | column (`blob`) with secondary index | CQL `SELECT ... WHERE field = token` | `cassandra-driver` |

The three SQL engines share the same standard-SQL adapter with only the driver and a few type names changed, so MySQL and MariaDB cost almost nothing to add on top of PostgreSQL. Range queries (Approach B, OPE field) use `WHERE field BETWEEN ? AND ?` on the SQL engines, `$gte/$lte` on MongoDB, and the equivalent N1QL/CQL range predicate; volume-hiding (Approach C) pads rows/documents per bucket identically in every engine. **Note:** Cassandra requires a secondary index (or a suitable partition-key design) for equality on a non-key field, and pure key-value stores such as Redis are excluded because they cannot answer an equality query over an encrypted field. Pina et al. [7], already cited in your literature review, implemented the AES-over-PostgreSQL variant of Approach B, giving a peer-reviewed precedent for the SQL leg.

### B.5 Dataset

- Use a **public, realistic dataset** with clearly sensitive attributes so leakage is meaningful and reproducible — e.g., a synthetic-but-realistic healthcare or e-commerce dataset, or a public Kaggle dataset (state the source and licence). The **same source records are loaded into every engine** (documents in MongoDB/Couchbase, rows in the SQL engines, wide-column rows in Cassandra) so the comparison is fair.
- Use **3 scale points** obtained by sub-sampling the dataset — **1k / 10k / ~29k records** (the ~29k being the full dataset) — so you can show how leakage-attack accuracy and performance overhead change with data size (feeds Results scalability discussion). The security (recovery-accuracy) result saturates well before 29k, so this range is sufficient for the attack; the scalability curve will be modest in magnitude, which should be stated plainly rather than over-claimed. If a larger stress point is wanted later, Synthea can generate additional rows without changing the pipeline, and that extra point can be run on the two primary engines only.
- Pick 1–2 **sensitive query fields** (e.g., `diagnosis`, `city`, `salary_band`) as the attack target.

### B.5.1 Dataset Sanity Check (do this before anything else)

Before building the workload, encryption, or adapters, the dataset must be validated, because the whole leakage-abuse attack depends on the sensitive field having the right statistical shape. If this check fails, the results will be meaningless (for example, the attack will look artificially strong or artificially weak for the wrong reasons), so this is a required gate, not an optional step. Run a short profiling script on the raw dataset and confirm the following, recording the results in the report so the choice of dataset is justified and reproducible:

1. **The sensitive field is categorical, not free text or unique.** The attack matches values by how often they occur, so the target field (e.g. `diagnosis`/`condition`, `city`) must be a repeating category. Check the number of distinct values: a handful to a few hundred is ideal. A field that is unique per row (names, IDs, timestamps) or free text cannot be attacked this way and must not be used as the target.

2. **The value distribution is skewed, not uniform.** Skew — some values very common, others rare — is exactly what a frequency- or count-matching attack exploits. Produce a frequency table and a histogram of the target field, and confirm it is uneven (ideally roughly Zipf-like). Report a simple skew indicator, for example the share taken by the top 10 values, or the ratio of the most common to the least common value. If the field is perfectly uniform, the attack has nothing to exploit and a different field or dataset should be chosen.

3. **There are enough distinct values to make recovery non-trivial but not impossible.** Too few categories (e.g. only 2–3, like a gender field) makes recovery trivial and uninteresting; too many near-unique values makes matching impossible. Aim for a field where the attacker has a real but non-trivial task.

4. **Data quality is acceptable.** Check for and record the proportion of missing/null values in the target field, obvious duplicates, and inconsistent encodings (e.g. `"NYC"` vs `"New York"`), since these distort both the attack and the frequency model. Decide and document how they are handled (dropped, normalised, or kept).

5. **The dataset is large enough for the chosen scale points and the field stays skewed after sub-sampling.** Confirm the full set covers the top scale point, and re-check the frequency shape on the 1k and 10k samples — the skew must survive sub-sampling, otherwise the smaller scale points will behave differently for the wrong reason. Use a fixed random seed when sampling so the scale points are reproducible.

6. **Auxiliary knowledge is realistic.** The attacker uses general knowledge of how common each value is. Confirm that such a distribution is plausibly knowable in the real world (e.g. disease prevalence, city population) so the threat model is credible, and note the source of that auxiliary distribution.

The profiling script (distinct-value count, frequency table, histogram, top-10 share, null rate) is written once and committed to the repo, so the sanity check is itself reproducible. Only after the target field passes this check are the workload, encryption, and adapters built on top of it.

### B.6 Query workload (identical across A/B/C)

- A fixed set of **equality queries** (and range queries if you include OPE) over the sensitive field(s), drawn to mimic a realistic, skewed access distribution (Zipf-like), because skew is what leakage-abuse attacks exploit.
- Fixed number of queries per run (e.g., 5,000), fixed seed, logged, and replayed **identically against all three approaches on every engine** (A/B/C × six engines). Store the workload file in the repo for reproducibility.

### B.7 The attack (this is what makes gap #1 measurable)

Implement a **documented access-pattern / volume leakage-abuse attack** as the *security metric generator*:

1. The adversary module records, for each observed query, the set/count of returned encrypted record IDs (access pattern + volume). This observation is **engine-independent** — the attacker sees the same access-pattern/volume signal whether the records came from a MongoDB collection or a PostgreSQL table, so the exact same attack code runs against both.
2. Using auxiliary knowledge of the field's value distribution, it matches observed query "fingerprints" to candidate plaintext values (a count/frequency-matching attack such as the classic **count attack** or a **Sap/IHOP-style** frequency-matching approach).
3. Output = **query-recovery accuracy (%)**: fraction of queries whose true plaintext value the adversary correctly recovered.
4. Run the *same* attack against A (should be ~100%, sanity check), B (expected high), and C (expected substantially lower) **on every engine**. The **drop in recovery accuracy from B to C is your headline security result**, and the fact that B leaks at similar accuracy across *all six* engines (and across both families) is your proof that the leakage is strategy-intrinsic, not engine-specific.

> Keep the attack faithful but simple: a frequency/count-matching attack is well documented, implementable in Python, and sufficient to show the effect. Cite the paper you base it on `[X4]`.

### B.8 Metrics and required outputs (feed Results Section 5)

**Raw metrics to log.** For every configuration (Approach A/B/C × 6 engines × 3 scale points × N repeats) the pipeline records:

*Security*
- Query-recovery accuracy (%) per approach, engine, and scale point.
- (Optional) value-recovery accuracy for the target field.

*Performance*
- Mean and p95 query latency (ms).
- Throughput (queries/sec).
- CPU utilisation (%) during the workload.
- Storage size: data + index (MB) and ciphertext expansion factor vs. plaintext.
- (Optional) client-side encryption time.

**Derived values to compute** (these are what the discussion is written around, so the pipeline should output them directly, not leave them to be worked out by hand):
- **Performance overhead of B and of C relative to A**, as a percentage, computed *per engine* against that engine's own plaintext baseline.
- **Storage-expansion factor** of B and C vs. A (×).
- **B→C recovery-accuracy drop**, in percentage points, per engine — the headline security number.
- **Range of Approach-B accuracy across the six engines** (min–max), to evidence cross-engine consistency.
- **Ranking of engines by Approach-C overhead** (which engine paid the least to reduce leakage).
- **Variance / confidence interval across the N repeated runs** for latency and recovery accuracy, so stability can be reported.

**Exact deliverables the Results section consumes.** The pipeline (or the analysis notebook) must emit the following, which map one-to-one onto Section 5:

| ID | Deliverable | Content |
|---|---|---|
| Table 1 | Performance per approach × engine (at the largest scale point) | latency, throughput, CPU, storage; three rows (A/B/C) per engine |
| Table 2 | Recovery accuracy per approach × engine (%) | one column each for A/B/C; one row per engine |
| Fig. 1 | Latency vs. dataset size (line chart) | x = 1k/10k/29k, y = mean latency, one line per approach (one chart per engine, or overlaid) |
| Fig. 2 | Recovery accuracy by approach × engine (grouped bar) | x = approach, bars = engines, y = recovery accuracy % |
| Fig. 3 | Security–performance trade-off (scatter) | x = overhead % vs. baseline, y = recovery accuracy %, one point per approach (per engine or averaged) |

Producing these five artefacts plus the derived values above is the definition of "done" for the experiment, and they are exactly the tables and figures the Results and Discussion section is built to receive. Export the raw per-run logs to CSV so all tables, figures, and derived values can be regenerated by a single analysis script for reproducibility.

### B.9 Tools & technologies

**Shared (engine-independent) core**
- **Python** — client-side encryption layer, query encoder, workload driver, and attack module (`cryptography`/`pycryptodome`, `numpy`, `pandas`). This code is written once and reused for every engine.
- **`psutil`** for CPU, Python `time.perf_counter` for latency, **`matplotlib`** for the Results figures.
- **Repo:** public GitHub with code, workload files, dataset link/loader, and a README with exact run steps for every engine (the assignment requires a public repo link).

**SQL engines**
- **PostgreSQL** (primary) — driver **`psycopg2`**; storage via `pg_total_relation_size()`/`pg_relation_size()`; query cost via `EXPLAIN ANALYZE` and `pg_stat_statements`. Optional `pgcrypto` for an in-DB AES variant of Approach B matching Pina [7].
- **MySQL** — driver **`mysql-connector-python`**; storage via `information_schema.TABLES` (`DATA_LENGTH` + `INDEX_LENGTH`); query cost via `EXPLAIN ANALYZE` / `performance_schema`.
- **MariaDB** — driver **`mariadb`** (the `mysql-connector` also works, as the protocol is shared); same measurement approach as MySQL. MariaDB is a near-twin of MySQL, so its adapter is essentially the MySQL adapter.

**NoSQL engines**
- **MongoDB** (primary, mandatory) — driver **`pymongo`**; storage via `db.collection.stats()`; ops/CPU via `mongostat`/`serverStatus`. Optionally note MongoDB's built-in **Queryable Encryption / CSFLE** as the real-world instance of Approach B.
- **Couchbase** — driver **`couchbase`** (Python SDK); queries in **N1QL/SQL++**; storage/latency via the Couchbase metrics API or the admin UI.
- **Cassandra** — driver **`cassandra-driver`**; queries in **CQL** (equality on a non-key field needs a secondary index); storage via `nodetool tablestats`.

All three SQL adapters are nearly identical (standard SQL, only the driver and a few type names change), and the two extra document/wide-column adapters follow the same `store()`/`query()` interface as MongoDB. Because the encryption, workload, and attack are shared code, each additional engine costs only one small storage adapter plus its measurement calls.

### B.10 Step-by-step execution (maps to Methodology 4.3)

1. **Objectives** — restate the measurable objectives from the Introduction (now including "hold across multiple SQL and NoSQL engines").
2. **Environment setup** — fixed VM/laptop spec (state RAM/cores); pinned versions of Python, **MongoDB, and PostgreSQL**.
3. **Data prep and sanity check** — load the same dataset into every engine at each scale point; identify the sensitive field(s); and **run the B.5.1 dataset sanity check first** (categorical, skewed, enough distinct values, acceptable quality, skew survives sub-sampling). Only proceed once the target field passes; record the profiling results for the report.
4. **Build the shared core** — encryption/bucketiser layer, query encoder, seeded workload driver, attack module (engine-independent).
5. **Build the two storage adapters** — MongoDB (`pymongo`) and PostgreSQL (`psycopg2`), each exposing `store()`/`query()` for approaches A/B/C.
6. **Workload generation** — generate and freeze one query set (seeded) used everywhere.
7. **Run performance experiments** — replay the workload on **A/B/C × {MongoDB, PostgreSQL} × 3 scale points × N repetitions**; log latency/throughput/CPU/storage.
8. **Run security experiments** — execute the leakage-abuse attack on A/B/C for **every engine**; record recovery accuracy.
9. **Analysis** — from the CSV logs, compute the derived values in B.8 (per-engine overhead of B and C, B→C accuracy drop, cross-engine accuracy range, run-to-run variance) and generate the five named deliverables: **Table 1, Table 2, and Fig. 1–3**. Compare overhead vs. **each engine's own plaintext baseline** and check cross-engine consistency of the leakage.
10. **Validation** — sanity-check A on every engine (attack ≈100%, latency lowest); compare overheads against published figures; repeat runs to report variance.
11. **Write-up** — feed tables/figures into Results; show the pipeline works for both SQL and NoSQL; link findings back to the literature review (leakage papers, performance papers).

### B.11 Team split (3 members, ~equal load)

- **Member 1 — Data, workload & repo:** dataset prep and loading into every engine, **the B.5.1 sanity check and profiling script**, scale points, seeded workload generator, repo/README.
- **Member 2 — Encryption & storage adapters:** shared client-side encryption layer (A/B/C) plus one small `store()`/`query()` adapter per engine (start with MongoDB + PostgreSQL, then MySQL/MariaDB/Couchbase/Cassandra) behind a single interface, and storage/latency instrumentation. *(The encryption is shared, so each extra adapter is a small addition — only the store/query functions differ per engine, and the three SQL adapters are nearly identical.)*
- **Member 3 — Adversary & analysis:** leakage-abuse attack module (engine-independent), metric collection, cross-engine plots, statistical validation.
- All three co-write the section that maps to their component.

### B.12 Expected results (hypotheses to confirm)

- A: recovery ≈ 100%, lowest latency/storage — the control (on every engine).
- B: near-baseline performance but **high** recovery accuracy → *querying leaks; encrypted ≠ confidential.*
- C: **markedly lower** recovery accuracy at the cost of higher latency and storage (padding) → *the confidentiality–performance trade-off, quantified on one common benchmark.*
- **Cross-engine:** the attack recovers plaintext at **similar accuracy across all six engines and both families** → the leakage is **strategy-intrinsic, not engine-specific** (this is the "works across SQL and NoSQL" proof your lecturer asked for, now demonstrated on six engines). The *performance* overhead, by contrast, varies by engine → the practical cost of confidentiality is engine-dependent even when the security behaviour is not, and the near-twin MySQL/MariaDB pair is a useful internal control.
- Recovery accuracy and overhead both shift with data scale, giving a scalability story.

This is exactly the "controlled, common-workload, common-threat-model comparison" your literature review says is missing — and demonstrating it on **six engines spanning both SQL and NoSQL families** turns your single global pipeline into a general result rather than a MongoDB-only artefact.

### B.13 Risks & limitations (pre-empt for Methodology 4.6 / Conclusion)

- **Synthetic/public data** may not mirror real skew — acknowledge and mitigate by testing a realistic distribution.
- **One attack ≠ all attacks** — your accuracy numbers are a lower bound on leakage; state this.
- **Approach C is a mitigation, not a proof of security** — frame it as *leakage reduction*, not elimination.
- **Single-server, honest-but-curious scope** — note that malicious or colluding adversaries are out of scope.
- **Cross-engine performance is not directly comparable** — the six engines have different query planners and storage formats, so raw millisecond/MB numbers should **not** be compared engine-to-engine. Report performance as **relative overhead against each engine's own plaintext baseline**; only the *security* results (recovery accuracy) are compared directly across engines. This keeps the cross-engine claim fair.
- **Scope of the extended engines** — the four additional engines (MySQL, MariaDB, Couchbase, Cassandra) may be run at fewer scale points or repeats than the two primary engines if time is constrained; this is a deliberate phasing choice (see B.2), not a flaw. Cassandra needs a secondary index for equality on a non-key field, and pure key-value stores (e.g., Redis) are out of scope because they cannot answer equality queries over an encrypted field.

---

### Marking-rubric checklist (Introduction, C2 = 3 marks)

- [x] **Overview of prior literature (1 mark)** — General Background connects DBMS → encryption → encrypted search, each cited.
- [x] **Problem statement (1 mark)** — decision-useful: names the "encrypted = secure" misconception and the missing common comparison, with consequences for long-term data-protection decisions.
- [x] **Objectives (1 mark)** — four explicitly measurable/testable objectives (accuracy %, latency ms, throughput, overhead %).
- [x] Supporting high-quality references (IEEE/ACM/Elsevier/Springer), IEEE in-text style, presented in logical order.
