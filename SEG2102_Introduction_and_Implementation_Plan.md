# SEG2102 — Introduction & Implementation Plan

**Working title:** *Beyond Confidentiality: Reducing and Measuring Access-Pattern, Volume, and Cross-Collection Metadata Leakage in Encrypted NoSQL Databases*

> **How to use this file.** Part A is the draft **Introduction (Section 2, worth 3 marks)** written to the marking rubric — paste it into your IEEE Word report and adjust citation numbers to match your group's shared reference list. Part B is a **detailed implementation plan** that turns your chosen domain gap (#1, leakage) plus the methodological "common-benchmark" gap into one **engine-agnostic pipeline you can build, run, and measure across three NoSQL database engines (MongoDB, Couchbase, Cassandra)** — satisfying the mandatory NoSQL requirement, measuring both the *before/after* impact of the leakage-reduction solution and its behaviour on a realistic *multi-collection* schema, so it feeds the Methodology (6 marks) and Results (10 marks) sections.
>
> **Citation placeholders:** references are written as `[X1]`, `[X2]`… where they are *new* sources the Introduction needs, and as `[LR-n]` where they should reuse a paper already in your literature review (e.g., Cao 2023, Gui 2023). Renumber everything into one IEEE sequence at the end.

---

## Part A — Introduction (Section 2)

The rubric breaks the 3 marks into three graded elements, each needing supporting references: **(i) overview of prior literature with connections to prior work**, **(ii) a problem statement that gives decision-useful insight**, and **(iii) measurable/testable objectives**. The draft below is organised so each element is unmistakable to the marker, mirroring the lettered-subsection style used in the lecturer's sample.

### 2. Introduction

#### General Background

Database Management Systems (DBMS) are the backbone of modern information infrastructure, responsible not only for storing and retrieving large volumes of data but also for enforcing data integrity, scalability, and access control [X1]. As organisations migrate sensitive workloads to cloud and outsourced environments, encryption has become the primary safeguard for confidentiality, ensuring that data remains unintelligible to any party without the decryption key even if the underlying storage is breached [LR-Mohamed]. This need is acute for NoSQL databases such as MongoDB, Couchbase, and Cassandra, whose document and wide-column models and horizontal scalability have made them a default choice for large-scale, cloud-hosted applications that routinely handle personal and regulated data [X2]. To protect such data while still allowing it to be queried, a family of techniques known collectively as *encrypted search* — including searchable symmetric encryption (SSE), order-preserving/order-revealing encryption (OPE/ORE), and deterministic encryption — has been developed so that a server can execute queries directly over ciphertext without ever holding the plaintext [LR-Ocenas], [X3].

#### Problem Statement

A widespread but dangerous assumption is that once data is encrypted, it is secure. In practice, the encrypted-search techniques that make querying possible do not achieve the semantic security of conventional encryption: they deliberately reveal auxiliary information — *access patterns* (which encrypted records a query touches), *search patterns* (whether two queries are identical), and *volume* (how many records a query returns) — so that the server can locate matching data efficiently [LR-Gui], [X3]. A growing body of *leakage-abuse* research has shown that an adversary who merely observes this leakage, without ever decrypting a single value, can reconstruct query contents and recover the underlying plaintext with high accuracy [LR-Gui], [X4]. Order-preserving schemes leak even more, as the ciphertext ordering exposes the distribution of the plaintext and enables inference attacks [LR-Cao]. The central problem is therefore twofold. First, **encrypted-query functionality is routinely treated as equivalent to confidentiality, when it is not** — a misconception with direct consequences for anyone making long-term decisions about how to protect regulated data in an outsourced DBMS. Second, **the leakage of competing schemes is reported under inconsistent datasets, query workloads, and threat models**, so a practitioner has no common basis on which to judge how much any given scheme actually leaks, or what it costs in performance to leak less [LR-Carvalho], [X4].

#### Significance of the Problem

This problem matters because the gap between *perceived* and *actual* security is exactly where real breaches occur. Regulations such as the GDPR and HIPAA treat encryption as a core safeguard for personal data [LR-Pina], yet an encrypted database that leaks access patterns can still expose which patients hold which diagnoses, or which customers transact with which partners, through inference alone — a disclosure that is invisible to conventional security testing and unaccounted for by compliance checklists [X4]. As encrypted NoSQL deployments scale into the cloud, the volume of observable query traffic grows, and with it the adversary's leverage for statistical inference [X2]. Providing decision-makers with a clear, measured picture of *what each encrypted-search approach leaks and what that protection costs* is thus essential for choosing defensible database designs, rather than relying on the false comfort that "the data is encrypted."

#### Objective

> **Engine scope (updated, see `SEG2102_MongoDB_Only_Plan.md` Revision 3):** multi-engine collection (MongoDB + Couchbase + Cassandra) proved too slow to complete reliably within the project timeline — Couchbase's missing secondary index alone cost significant time before being diagnosed. The study below was therefore run to completion **in MongoDB only**, which has complete, clean data across all three scale points (1k/10k/30k) and the full decoy-ratio sweep. Couchbase/Cassandra (and an experimental ArangoDB adapter) remain in the codebase as an **optional generalisation appendix**, evaluated only as a lightweight single-point check where time permits, not as a required part of the core result. The pipeline's engine-agnostic client/adapter split means this is a scoping decision, not a redesign — extending to another engine is implementation cost, not new architecture.

The objective of this report is to **design, implement, and evaluate a leakage-reduction solution for encrypted NoSQL databases, quantify its confidentiality–performance trade-off, and show that it works both for a single collection and for a realistic multi-collection schema in MongoDB, with generalisation to Couchbase and Cassandra explored as a secondary check where time permits.** Concretely, the study will:

1. Implement three query-able storage approaches — a baseline plaintext store (A), a deterministic/property-preserving scheme that still leaks (B), and the leakage-reduced solution (C) — as **one engine-agnostic pipeline** applied to the same dataset and workload across **three NoSQL engines (MongoDB, Couchbase, Cassandra)**.
2. **Measure leakage quantitatively** by running a documented access-pattern / volume / frequency inference attack against each approach, reporting the adversary's query-recovery accuracy, and measuring the **impact of the solution as a before (B) vs after (C) comparison** on every metric.
3. **Measure the performance cost** of the solution under an identical workload using query latency, throughput, CPU utilisation, and storage/ciphertext expansion, reported as the before/after change from B to C.
4. **Extend the evaluation from a single collection to a realistic three-collection schema** (`patients`, `lab_orders`, `billing`) and show that the solution reduces both per-collection value leakage and **cross-collection linkage leakage**, demonstrating that it is flexible enough for real multi-table deployments while remaining consistent across all three NoSQL engines.

These objectives are measurable and testable: each yields numeric metrics (recovery accuracy in %, linkage-recovery accuracy in %, latency in ms, throughput in ops/s, overhead in %) that can be compared against each engine's plaintext baseline and as a before/after (B vs C) change, supporting the conclusions drawn in Section 5.

#### Scope of the Report

This report focuses on **single-server, outsourced encrypted search in NoSQL databases** and the leakage that arises from querying encrypted data. The study implements one common pipeline and evaluates it fully on **MongoDB**, the sole engine with complete, reproducible data across all scale points and the full decoy-ratio sweep, for both a single collection and a realistic three-collection schema. The pipeline's client/adapter split makes it engine-agnostic by design, and this was partially validated during development against Couchbase and Cassandra (and an experimental ArangoDB adapter) before those were descoped for time — cite whatever single-point Couchbase/Cassandra data is included in the optional appendix, if run. It covers deterministic/property-preserving encryption (B) and the leakage-reduced solution (C: salted/re-randomised encryption, bucket padding, per-collection keys, and name tokenisation), evaluates them against a defined honest-but-curious adversary using a known inference attack, and reports security (value-recovery and cross-collection linkage-recovery accuracy) and performance metrics, including the before/after impact of the solution. It **substantially reduces but does not claim to fully eliminate** leakage: fully hiding the raw access pattern requires ORAM-class techniques whose cost is impractical, and **network-level metadata (traffic timing, packet sizes) is below the database layer and is left as future work**. Fully homomorphic and trusted-execution-environment approaches, secure multi-party computation, and multi-user key distribution are also out of scope (the first two are reviewed in the literature review as alternative paradigms).

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

This plan operationalises **domain gap #1 (encrypted-query functionality leaks information and is not equivalent to confidentiality)**. The creative contribution is a **leakage-reduction solution that uses generatively-produced decoy records to flatten the frequency/volume signal that leakage-abuse attacks exploit, combined with a secret client-only function that decides which records are real** so that the untrusted server (and any attacker) cannot separate real data from decoys. The solution is built and measured as one engine-agnostic pipeline across **three NoSQL engines — MongoDB, Couchbase, and Cassandra** — for both a single collection and a realistic three-collection schema, and every result is reported as a **before vs. after** comparison so readers can see exactly what the solution changes.

**Honest positioning.** This project does not invent a new cryptographic primitive, and it does not claim to *eliminate* leakage. Hiding the raw physical access pattern completely requires ORAM-class techniques whose cost is provably at least logarithmic and impractical for a real database, and network-level metadata (traffic timing, packet sizes) sits below the database layer. The contribution is therefore framed as: **a novel application of generative decoy insertion to access-pattern/volume leakage, evaluated under a common benchmark across NoSQL engines and across single- and multi-collection schemas — a setting prior work has not measured.** How this relates to existing work is set out in B.13.

### B.1 Core idea in one sentence

> Store the same data four ways — (A) plaintext, (B) deterministic encryption that still leaks, (C) deterministic encryption plus *naive* decoy padding, and (D) our solution: deterministic encryption plus *generatively-produced* decoys whose real/decoy status is decided by a secret client-only function — then run one identical inference attack (single-collection value recovery and cross-collection linkage recovery) across MongoDB, Couchbase, and Cassandra, and report security and performance as a before/after comparison.

The reason C and D both exist is that they isolate the value of the creative part: **C shows that naive decoys can be filtered out by an attacker who checks whether records look realistic, whereas D's generative decoys survive that filter.** The gap between C and D is the headline contribution.

### B.2 Research design

- **Type:** Quantitative, experimental comparative study.
- **Independent variables:** (1) approach (A / B / C / D); (2) NoSQL engine (MongoDB primary and fully evaluated; Couchbase/Cassandra optional appendix, see Scope); (3) schema (single collection vs. three linked collections); (4) data scale (sub-sampled points, see B.5); (5) **`decoy_ratio` ∈ {0.5, 0.75, 1.0}** — how far each value's observed count is padded toward the most frequent value's count, for approaches C/D. Added as a formal independent variable rather than a fixed constant because the sweep produced the report's strongest finding: recovery does not fall gradually with the ratio, it stays roughly flat at 0.5–0.75 and collapses only at full flattening (1.0) — a cliff, not a slope.
- **Dependent variables — security:** value-recovery accuracy (%), and cross-collection linkage-recovery accuracy (%). **Performance:** mean/p95 query latency (ms), throughput (q/s), CPU (%), storage (MB) and expansion factor.
- **Held constant:** dataset, seeded workload, hardware, engine versions, warm-up, repeats — so only the variables above move.
- **Threat model:** an honest-but-curious server/observer who sees the encrypted collections, the encrypted queries, and which encrypted records each query returns (access pattern + volume + search pattern), plus realistic auxiliary knowledge of the value distribution. For approaches C and D the attacker is additionally allowed a **realism filter** — the ability to discard records that look statistically implausible — which is what separates naive decoys (C) from generative decoys (D).
- **Phasing:** MongoDB is the mandatory primary engine and is run fully (all approaches, schemas, scales, repeats). Couchbase and Cassandra are the extension; if time is short they may be run at the largest scale only, stated openly as a scoping choice.

### B.3 System architecture

The trusted client holds all keys and secret functions; the untrusted server only stores and returns data. Only the boxed storage adapter changes per engine.

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                         CLIENT (trusted)                                 │
   │  ┌────────────┐ ┌──────────────┐ ┌───────────────┐ ┌─────────────────┐  │
plaintext│ Value       │ │ GAN decoy    │ │ Secret ID     │ │ Query encoder + │ │
records─▶│ encryptor   │ │ generator    │ │ function f_k  │ │ workload driver │ │
   │  │ (per-coll.) │ │ (realistic   │ │ (real vs      │ │                 │  │
   │  │             │ │  fake rows)  │ │  decoy)       │ │                 │  │
   │  └────────────┘ └──────────────┘ └───────────────┘ └────────┬────────┘  │
   └───────────────────────────────────────────────────────────┼───────────┘
                    real + decoy records (indistinguishable)     │ enc. query
                    ┌─────────────────┬──────────────────────────┼───────────┐
                    ▼                 ▼                           ▼           │
             ┌────────────┐    ┌────────────┐             ┌────────────┐      │
             │ Adapter:   │    │ Adapter:   │             │ Adapter:   │      │
             │ MongoDB    │    │ Couchbase  │             │ Cassandra  │      │
             └─────┬──────┘    └─────┬──────┘             └─────┬──────┘      │
                   └─────────────────┴────────┬─────────────────┘             │
                        returns reals+decoys  │ (observed by attacker)        │
                                              ▼                               │
   ┌────────────────────────────────────────────────────────────────────────┐
   │  On the client: recompute f_k(id) → keep REAL records, drop decoys,      │
   │  decrypt values, return clean result to the user.                        │
   └────────────────────────────────────────────────────────────────────────┘

   Attacker sees only the server side: encrypted records (reals+decoys mixed),
   encrypted queries, and result sets. It cannot compute f_k (no key).
```

### B.4 The four approaches

| Approach | What is stored | Purpose | Expected leakage |
|---|---|---|---|
| **A — Plaintext** | Sensitive field in the clear | Baseline / attack sanity check (≈100% recovery) | Full |
| **B — Deterministic** | Value encrypted; same value → same token | Represents common "encrypted database" practice | High: frequency + volume + linkage leak |
| **C — Naive decoys** | B + random/simple decoy records to flatten frequency | Baseline defence; shows decoys help but are filterable | Reduced, but a realism-filtering attacker recovers much of it |
| **D — Generative decoys (our solution)** | B + GAN-generated realistic decoys + secret real/decoy ID function + per-collection keys + name tokenisation | The contribution | Substantially reduced and *resistant* to the realism filter |

Approach **D** combines four layers, each closing one leak:

1. **Value encryption (per-collection keys).** The sensitive field is encrypted so equality queries still work, but with a *different key per collection*, so the same value (e.g. a `patient_code`) becomes a different token in `patients`, `lab_orders`, and `billing` — this breaks cross-collection linkage.
2. **Generative decoy insertion.** A small generative model (see B.4.2) produces realistic fake records, added preferentially for rare values so the observed frequency of every value is flattened toward uniform — this hides the frequency/volume signal.
3. **Secret real/decoy ID function (see B.4.1).** Which records are real is decided by a keyed function only the client can compute, so the server cannot filter decoys out.
4. **Name tokenisation.** Collection and field names are replaced by opaque tokens (`col_9f3a`, `f_22b1`) via a client-held map, so structural metadata (a collection literally named `hiv_patients`) does not leak. This layer is *demonstrated*, not scored.

### B.4.1 The secret real/decoy identification function (the "formula")

Every record — real or decoy — is stored on the server with an opaque identifier that looks random. The client **generates** these identifiers directly from a secret keyed formula, so that the client alone can later recompute exactly which identifiers it created and which of them are decoys, while the server and any attacker see one uniform, indistinguishable pool of records.

**Definition.** Let `k` be a secret key generated on the client and never sent to the server. Records are created in a fixed sequence with a counter `i = 0, 1, 2, …`. For each record the client derives its server-visible identifier and its real/decoy status from `k` and `i`:

```
id(i)     =  HMAC_SHA256(k,  "id"  || i)              (truncated to the ID length)
isDecoy(i) = 1   if   ( HMAC_SHA256(k, "tag" || i)  mod  (d + 1) )  ==  0
             0   otherwise
```

where:
- `HMAC_SHA256(k, ·)` is a keyed hash (a standard pseudo-random function); without `k` its output is computationally indistinguishable from random, so both the identifiers and the real/decoy pattern look random to anyone but the client,
- `||` denotes concatenation, and the fixed strings `"id"` / `"tag"` domain-separate the two uses of the key,
- `d` sets the decoy ratio: on average 1 decoy for every `d` real records (e.g. `d = 3` → about one quarter of records are decoys).

Because **both** real and decoy identifiers are produced by the *same* formula `id(i)`, they are drawn from the same space and are indistinguishable on the server; only the separate, secret `isDecoy(i)` bit — which is never stored — tells them apart.

**How records are created.** The client walks the counter `i`. For each `i` it computes `id(i)` and `isDecoy(i)`: if `isDecoy(i) = 0` it stores the next real record under `id(i)`; if `isDecoy(i) = 1` it stores a generative decoy (see B.4.2) under `id(i)`. No guessing or rejection sampling is needed — every identifier is produced deterministically from the key and the counter.

**How the user gets the right data back.** The client only needs to keep `k` and the current counter value. To recover its data it regenerates the identifiers, and for any record returned by a query it recomputes `isDecoy` for that identifier's index: it **keeps the real records, discards the decoys, decrypts the values, and returns the clean result to the user.** Equivalently, since the mapping is deterministic, the client can precompute the set of real identifiers directly from `k`. The user therefore always sees correct, decoy-free data.

**Why the attacker cannot do the same.** Regenerating or classifying the identifiers requires the secret key `k`. Without it, both `id(i)` and `isDecoy(i)` are pseudo-random, so the attacker sees a uniform pool of random-looking identifiers and cannot tell which were client-generated as real and which as decoy. This is the asymmetry that makes the scheme work: **the same secret that protects the data also generates, and conceals, which records are real.** (A simpler variant stores an encrypted flag `AES_enc(k, is_real)` in each record and filters on the decrypted flag; the generative keyed form above is preferred because the real/decoy partition is *derived from the key*, not stored anywhere, so there is nothing extra on the server for an attacker to target.)

This formula is written once, lives only in the client code, and its key is held only on the client — satisfying the requirement that *only the user site can generate the decoy and real identifiers and later recompute which is which.*

### B.4.2 The generative decoy model

The decoys must be **realistic complete records**, not just padded values, otherwise the attacker's realism filter (allowed in the threat model) discards them — which is exactly the weakness of Approach C. A small generative model is trained on the real records to learn the joint distribution of the fields (e.g. that a given `specific_diagnostic_test` co-occurs with plausible `age_category`, `race_category`, and companion tests). It then generates fake records that are individually plausible. The *targeting policy* decides how many decoys to generate for each value so that the aggregate frequency is flattened. Together: the model gives per-record realism (defeats the filter), and the targeting gives aggregate frequency-flattening (defeats the count attack).

A full GAN is not required for the effect; a lightweight generative model (a small tabular GAN such as CTGAN, or a simpler conditional sampler that preserves field co-occurrence) is sufficient and keeps the build achievable. The choice is recorded in the report, and Approach C uses a deliberately naive generator (independent random field values) so the C-vs-D comparison isolates the value of realistic generation.

### B.5 Dataset

- The project uses the profiled healthcare dataset (source: the supplied Excel file, **826,843 records**), with **`specific_diagnostic_test`** as the primary sensitive/attack field (297 distinct values, strongly skewed — see B.5.1) and **`patient_code`** as the key that links the three collections.
- **Three-collection schema** derived from the dataset, linked by `patient_code`: `patients` (one row per patient with `race_category`, `age_category`), `lab_orders` (one row per test event with `specific_diagnostic_test`, `diagnostic_test_category`), and `billing` (one row per test event with a derived cost field). The single-collection tests use `lab_orders` alone.
- **3 scale points** by sub-sampling — **1k / 10k / full (826,843)** — with a fixed seed, so scalability can be shown. The security result saturates well before the full size; the largest point is the stress/scalability point and may be run on the primary engine only.

### B.5.1 Dataset Sanity Check (already completed — gate before building)

The sanity check from the plan has been run and passed, and its results are recorded for the report: `specific_diagnostic_test` has **297 distinct values** (categorical, in the ideal range), **top-10 share 59%** and **max/min frequency ratio ~99,000×** (strongly skewed — exactly what the attack needs), **0% nulls**, and the skew **survives sub-sampling** (top-10 share ~59% at 1k, 10k, and full). Auxiliary knowledge (relative test-ordering frequencies) is realistic, analogous to published lab-utilisation statistics. Rejected alternatives (`diagnostic_test_category`, `race_category`, `age_category`) had too few categories or weaker skew. This validation justifies the field choice and must be reproduced by the committed profiling script.

**`billing`'s derived `cost_category` field (multi-collection schema only) has a documented issue of its own, alongside the rejected fields above.** It was originally constructed with `pd.qcut` (equal-count quantile bins), which is uniform by definition and therefore has no real skew for decoys to flatten — a construction artifact, not a security result, if left as-is. This has since been fixed in code: `cost_category` is now built with fixed dollar-threshold tiers (`pd.cut`), carrying genuine skew from the underlying per-test cost distribution, and its recovery numbers now do move with the decoy ratio. It remains outside the headline value-recovery comparison regardless, since at only 4 candidate values it is still lower-cardinality than the vetted `specific_diagnostic_test`; it is reported as a supplementary, non-headline table.

### B.6 Query workload (identical across A/B/C/D)

- A fixed set of **equality queries** over `specific_diagnostic_test` (single-collection) and over `patient_code` (for the cross-collection linkage test), drawn from a realistic skewed (Zipf-like) access distribution.
- Fixed number of queries per run (e.g. 5,000), fixed seed, logged, and replayed identically against every approach on every engine. The workload file is committed for reproducibility.

### B.7 The attacks (what makes the leakage measurable)

Two attacks, both from the standard leakage-abuse literature, run identically on all approaches and engines:

1. **Single-collection value recovery.** The attacker observes, per query, which encrypted records return and how many (access pattern + volume), and matches the observed frequency of each token to the known value distribution (a count/frequency-matching attack). Output: **value-recovery accuracy (%)**. For C and D the attacker first applies the **realism filter** to try to discard decoys before matching.
2. **Cross-collection linkage recovery.** The attacker tries to link records belonging to the same `patient_code` across `patients`, `lab_orders`, and `billing` by spotting identical tokens or correlated access. Output: **linkage-recovery accuracy (%)** — the fraction of true cross-collection links the attacker reconstructs. Per-collection keys in Approach D are what this measures the effect of.

Sanity check: Approach A must give ≈100% on the value attack; if not, the attack code is wrong.

### B.8 Metrics and required outputs (feed Results Section 5)

**Security metrics:** value-recovery accuracy (%), linkage-recovery accuracy (%), each per approach, engine, schema, and scale; plus the **B→D and C→D drops** (percentage points) as the headline numbers.

**Performance metrics:** mean/p95 latency, throughput, CPU, storage + expansion factor, reported as **before/after (B vs D) change** per engine against that engine's own plaintext baseline.

**Derived values the pipeline outputs directly:** per-engine latency/storage overhead of C and D vs A; B→D and C→D accuracy drops; the range of results across the three engines (consistency); run-to-run variance across repeats.

**Named deliverables for Section 5:**

| ID | Deliverable | Content |
|---|---|---|
| Table 1 | Performance per approach × engine (largest scale) | latency, throughput, CPU, storage; four rows (A/B/C/D) per engine |
| Table 2 | Value-recovery accuracy per approach × engine (%) | one column each A/B/C/D; one row per engine |
| Table 3 | Cross-collection linkage-recovery accuracy, before (B) vs after (D) | per engine, three-collection schema |
| Fig. 1 | Latency vs. dataset size (line) | x = 1k/10k/full, y = latency, one line per approach |
| Fig. 2 | Value-recovery accuracy by approach × engine (grouped bar) | shows the B→C→D reduction, and that C is defeated by the realism filter while D is not |
| Fig. 3 | Security–performance trade-off (scatter) | x = overhead % vs. baseline, y = recovery accuracy %, one point per approach |
| **Fig. 4** | **Before/after DATA view** | a single example record shown in each state: plaintext (A), encrypted (B), and encrypted-with-solution (D), side by side, so readers see what changes |
| **Fig. 5** | **Before/after METADATA view** | (a) frequency histogram of the sensitive field before (skewed) vs. after decoys (flattened); (b) a linkage diagram showing the same `patient_code` sharing one token across collections before, vs. different tokens after; (c) collection/field names before vs. tokenised after |

Export all raw per-run logs to CSV so every table and figure regenerates from one analysis script.

**The before/after visualisations (Fig. 4 and Fig. 5) are a required output**, because the whole point of the study is to *show* the difference the solution makes. Fig. 4 makes the record-level change concrete (readable value → ciphertext → ciphertext-plus-hidden-decoys). Fig. 5 makes the metadata-level change concrete: the flattened histogram is the visual proof that frequency leakage is gone, and the linkage diagram is the proof that cross-collection linkage is broken.

### B.9 Tools & technologies

**Shared core (Python):** value encryption (`cryptography`/`pycryptodome`), the `HMAC`/`hashlib` secret ID function, the generative decoy model (`ctgan`/`sdv` for a small tabular GAN, or a custom conditional sampler with `numpy`/`pandas`), the workload driver, and the two attack modules. Written once, reused for all engines.

**NoSQL engines & drivers:** MongoDB (`pymongo`; storage via `db.collection.stats()`), Couchbase (`couchbase` SDK, N1QL/SQL++), Cassandra (`cassandra-driver`, CQL with a secondary index for equality on the sensitive field; storage via `nodetool tablestats`).

**Measurement & output:** `psutil` (CPU), `time.perf_counter` (latency), `matplotlib` (all figures, including the before/after views). Public GitHub repo with code, the seeded workload, the profiling script, the dataset loader, and a README with exact run steps.

### B.10 Step-by-step execution

1. **Environment setup** — fixed hardware; pinned versions of Python, MongoDB, Couchbase, Cassandra.
2. **Data prep + sanity check** — build the three-collection schema (linked by `patient_code`); the B.5.1 sanity check is already passed and its script is committed.
3. **Build the shared core** — value encryptor (per-collection keys), the secret ID-generation function `id(i)`/`isDecoy(i)` (B.4.1), the generative decoy model, the query encoder, the two attack modules.
4. **Build the three storage adapters** — MongoDB, Couchbase, Cassandra (`store()`/`query()` behind one interface).
5. **Build the four approaches** — A plaintext; B deterministic; C deterministic + naive decoys; D deterministic + generative decoys + secret IDs + per-collection keys + name tokenisation.
6. **Workload generation** — one seeded query set, frozen and committed.
7. **Run performance experiments** — replay the workload for A/B/C/D × 3 engines × scales × repeats; log latency/throughput/CPU/storage.
8. **Run security experiments** — value-recovery attack (with realism filter for C/D) and cross-collection linkage attack on every configuration; log recovery accuracies.
9. **Analysis** — compute derived values and generate Tables 1–3 and Figs 1–5 (including the before/after data and metadata views) from the CSV logs.
10. **Validation** — sanity-check A (≈100% recovery, lowest latency); repeat runs and report variance; compare overheads to the literature.
11. **Write-up** — feed all deliverables into Results; link back to the objectives and to prior work (B.13).

### B.11 Team split (3 members)

- **Member 1 — Data, schema, workload, repo:** three-collection build, sanity-check script, seeded workload, before/after data/metadata visualisations (Fig. 4–5), repo/README.
- **Member 2 — Crypto & solution:** value encryption + per-collection keys, the secret ID-generation function (B.4.1), the generative decoy model, and the three engine adapters.
- **Member 3 — Attacks & analysis:** value-recovery and linkage attacks (incl. realism filter), metric collection, Tables 1–3, Figs 1–3, statistical validation.

### B.12 Expected results (hypotheses to confirm)

- **A:** ≈100% recovery, fastest/smallest — control.
- **B:** high value-recovery and high linkage-recovery → *encrypted data still leaks when queried.*
- **C/D vs. `decoy_ratio` (confirmed, MongoDB, `lab_orders`):** recovery does **not** fall gradually as the decoy ratio increases from 0.5 to 1.0 — it stays roughly flat (~93%→~33–40%) at 0.5–0.75, then **collapses sharply only at full flattening (ratio = 1.0)**. This is a cliff, not a slope, and it is the single strongest result in the study. Under full flattening, the C-vs-D contrast is exactly as hypothesised: naive decoys (**C**) are still partially recoverable once the attacker applies the realism filter (filtered ≈ 22%), while generative decoys (**D**) stay at 0% even under the filter. **This C→D gap under the realism filter at the cliff (≈22 percentage points) is the headline contribution number.**
- **Linkage:** A/B/C ≈ 100%, **D collapses to 0%** (per-collection keys), confirmed **consistent across all three scale points (1k/10k/30k)** — a clean, scale-independent result.
- **Cross-engine consistency:** only partially evaluated (see Scope) — MongoDB is the fully confirmed engine; the same pattern is expected, not yet re-confirmed end-to-end, on Couchbase/Cassandra if the optional appendix is run.
- **Before/after views:** the histogram visibly flattens (frequency leak removed) and the cross-collection tokens visibly diverge (linkage broken).

### B.13 Relation to prior work (novelty scoping — put a short version in the report)

The building blocks are established and **must be cited**, not claimed: the frequency/count attack on deterministic encryption is from Naveed, Kamara & Wright (ACM CCS 2015); the limits of padding-style defences are from Cash et al. (2016); volume-hiding for multi-maps is from Patel, Persiano, Yeo & Yung (ACM CCS 2019). What this project contributes is **not a new primitive** but (i) using a *generative model* to produce decoys that resist a realism-filtering attacker — an application not covered by the padding/decoy literature; (ii) a *common-benchmark* evaluation across three NoSQL engines (document and wide-column), where prior work is almost entirely SQL/abstract; and (iii) a combined single- and multi-collection measurement with an explicit before/after view. This framing is honest and defensible: it is novel as an application and setting, and citing the prior attacks strengthens rather than weakens the report.

### B.14 Risks & limitations (pre-empt for Methodology / Conclusion)

- **Reduces, does not eliminate.** The raw physical access pattern is only fully hidden by ORAM-class methods (proven ≥ logarithmic overhead); this solution lowers *measured* recovery, and the residual is stated plainly.
- **One attack family = a lower bound.** Recovery accuracy is a lower bound on true leakage; other attacks may do better.
- **Decoys cost resources.** Extra storage, bandwidth, and client-side filtering — measured explicitly as the Approach-D overhead.
- **Generative-model quality bounds the defence.** If the generator is poor, decoys become filterable; the C-vs-D comparison makes this dependency visible rather than hiding it.
- **Network-level metadata (timing, packet sizes) is out of scope** (below the DB layer) and named as future work, alongside reactive detect-and-respond defences against active attackers.
- **Cross-engine performance is not directly comparable** (different planners/storage); compare only relative overhead vs. each engine's own baseline, while security results are compared directly across engines.

---

### Marking-rubric checklist (Introduction, C2 = 3 marks)

- [x] **Overview of prior literature (1 mark)** — General Background connects DBMS → encryption → encrypted search, each cited.
- [x] **Problem statement (1 mark)** — decision-useful: names the "encrypted = secure" misconception and the missing common comparison.
- [x] **Objectives (1 mark)** — measurable/testable (recovery %, linkage %, latency, overhead %), now including the before/after and multi-collection dimensions.
- [x] Supporting high-quality references (IEEE/ACM/Elsevier/Springer), IEEE in-text style, in logical order.
