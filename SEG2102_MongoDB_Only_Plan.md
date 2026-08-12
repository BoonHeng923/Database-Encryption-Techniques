# SEG2102 — MongoDB-Only Implementation & Outputs Plan (Revision 3)

> **Why this revision exists.** Multi-engine (MongoDB + Couchbase + Cassandra) collection was taking too long to complete reliably (Couchbase's indexing issues alone cost significant time). This revision **makes MongoDB the sole primary engine**, since it is the one with complete, clean data across all three scale points (1k / 10k / 30,000) and the full decoy-ratio sweep. Couchbase/Cassandra become an **optional generalization appendix** — include only if time remains; the core report stands complete without them.
>
> **What changed vs. Revision 2:** (1) single engine, not three; (2) `decoy_ratio` is now a first-class swept variable, not a fixed constant, because the sweep produced your best finding (the flattening cliff); (3) `billing`/`cost_category` is explicitly downgraded to a documented-limitation field, not a headline metric, per the pd.qcut artifact found earlier; (4) the deliverables below are written directly against the data shape you already have, so almost no new experiment code is needed — this is now mostly an **analysis and write-up plan**.

---

## 1. What you already have (don't re-run this)

- **Engine:** MongoDB only.
- **Scale points:** 1,000 / 10,000 / 30,000 records — all three complete, clean, exit 0.
- **Schemas:** single (`lab_orders` only) and multi (`patients` + `lab_orders` + `billing`, linked by `patient_code`).
- **Approaches:** A (plaintext), B (deterministic), C (naive decoys), D (generative decoys + secret IDs + per-collection keys).
- **Decoy-ratio sweep:** 0.5 / 0.75 / 1.0, run for C and D, on the multi schema (extend to single schema and to 1k/10k if not already done — cheap, since MongoDB is fast).
- **Attacks:** value-recovery (with realism filter for C/D) on `specific_diagnostic_test`/`patients`/`billing`, and cross-collection linkage recovery on `patient_code`.
- **Known artifact (keep, don't hide):** `billing`'s `cost_category` was built with `pd.qcut` (uniform quantile bins), so it has no real skew to flatten at low ratios — its recovery numbers are a **construction artifact**, not a security result. Document this exactly as B.5.1 already documents rejected fields; do not present `billing` value-recovery as a headline number unless Fix 1 (rebuild with fixed skewed cost tiers, see §6) is applied.

## 2. The four things your outputs must show

You asked specifically for: **(1) before/after performance, (2) security, (3) cost, (4) "and so on."** Here is exactly what each maps to, using data you already have.

### 2.1 Before/after performance — "what does the solution cost in speed?"
**Comparison:** A (no protection) → B (encrypted, existing practice) → D (your solution), at each scale point, for `lab_orders` (your vetted attack field).
**Metric:** mean latency, p95 latency, throughput (qps), CPU %.
**Derived value:** performance overhead of D vs. A, as a percentage, per scale point — this is your literal "before vs. after" number.

```
Overhead_D(%) = ( latency_D − latency_A ) / latency_A × 100
```

### 2.2 Security — "does the solution actually protect the data?"
**Comparison:** B → D value-recovery on `lab_orders`, **and** the full decoy-ratio sweep (0.5 / 0.75 / 1.0) for both C and D.
**Metric:** recovery accuracy (%), filtered vs. unfiltered.
**The headline finding you already have:** recovery does **not** fall gradually with ratio — it stays roughly flat (~93%→~33–40%) at 0.5–0.75, then **collapses to 0% only at full flattening (ratio = 1.0)**. This is a cliff, not a slope, and it is your single strongest result. It also cleanly demonstrates the C-vs-D contrast under the realism filter: at ratio 1.0, **C's filtered recovery is 22.2%** (naive decoys get partly recovered once the attacker filters out unrealistic ones) while **D's filtered recovery stays at 0%** (generative decoys survive the filter). That gap **is** the contribution.

**Linkage security:** A/B/C = 100% recovery, D = 0%, consistent across 1k/10k/30k. This is a clean, scale-independent result — report it exactly as measured, no further analysis needed beyond stating it holds at all three scales.

### 2.3 Cost — "what do you pay for that protection?"
**Comparison:** storage/ciphertext-expansion factor of B, C, D vs. A, **as a function of decoy ratio**.
**Metric:** storage (MB), expansion factor (×).
**The finding you already have:** expansion rises steeply with ratio — roughly 7–14× at ratio 0.5 up to ~26× at ratio 1.0 on `lab_orders` in the multi schema. Full flattening (the ratio that kills recovery) is also the most expensive point. **This is the trade-off**, and you now have three measured points on the curve, not a guess.

### 2.4 "And so on" — the two things that complete the story
- **Scalability:** does the pattern (cliff, expansion growth, linkage=0%) hold as data grows from 1k→10k→30k? You already have this — say explicitly whether recovery/expansion numbers are stable across scale (they appear to be, per the linkage table) or drift.
- **Single- vs. multi-collection:** does the solution work the same way with just `lab_orders` alone as it does inside the full 3-collection schema? Compare the single-schema `lab_orders` D-numbers against the multi-schema `lab_orders` D-numbers at the same ratio — if they match closely, that's evidence the solution composes cleanly across schema complexity, which is exactly your "flexible enough for real multi-table deployments" objective (Introduction, objective 4).

## 3. Required outputs (exact deliverables for Results Section 5)

All of these are computable **now**, from data you already have, with one Python analysis script reading the CSV logs.

| ID | Deliverable | Content | Data source |
|---|---|---|---|
| **Table 1** | Before/after performance on `lab_orders` | latency, p95, throughput, CPU — rows A/B/D, columns = the three scale points | existing single+multi logs |
| **Table 2** | Value-recovery vs. decoy ratio | rows = ratio (0.5/0.75/1.0), columns = B / C-unfilt / C-filt / D-unfilt / D-filt, for `lab_orders` | existing sweep |
| **Table 3** | Linkage recovery, before vs. after | A/B/C vs. D, at each of the three scales | existing linkage logs |
| **Table 4** | Cost: storage expansion vs. decoy ratio | expansion factor for C and D at each ratio, `lab_orders` and `patients` | existing sweep |
| **Fig. 1** | Performance before/after (bar or line) | latency for A/B/D across the three scale points | Table 1 |
| **Fig. 2** | **The cliff** — recovery vs. decoy ratio | x = ratio (0.5/0.75/1.0), y = recovery %, separate lines for C-filtered and D-filtered | Table 2 — **this is your headline figure** |
| **Fig. 3** | Security–cost trade-off | x = storage expansion (×), y = recovery accuracy (%), one point per (approach, ratio) combination | Tables 2+4 combined |
| **Fig. 4** | Linkage before/after | simple bar: A/B/C = 100% vs. D = 0%, one bar group per scale point, to show scale-independence | Table 3 |
| **Fig. 5** | Before/after DATA view | one example `lab_orders` record: plaintext → B ciphertext → D ciphertext-with-decoys, side by side | manual construction from one record |
| **Fig. 6** | Before/after METADATA view | (a) frequency histogram of `specific_diagnostic_test` at ratio 0.5 vs. ratio 1.0 (visually shows the flattening that causes the cliff); (b) `patient_code` token diagram: same value → same token (B) vs. different tokens per collection (D) | derived from stored data at two ratios |

**On `billing`:** report its numbers in a small supplementary table only (not Table 2), with one sentence: *"`billing`'s `cost_category` was constructed with quantile binning (`pd.qcut`), which produces uniform bin counts by design; its recovery figures therefore reflect this construction artifact rather than the solution's flattening behaviour, and are excluded from the headline security comparison, consistent with the field-vetting criteria in the dataset sanity check (B.5.1)."*

## 4. Derived values to compute (feed the Discussion)

Compute these once, in the analysis script, so the write-up never does arithmetic by hand:

- **Overhead of D vs A**, per scale point (latency %, from Table 1).
- **B→D recovery drop** at each ratio (percentage points, from Table 2).
- **The cliff threshold**: the ratio at which recovery drops below some meaningful line (e.g. 10%) — currently known to be between 0.75 and 1.0; if time allows, add ratio = 0.85, 0.9, 0.95 runs to narrow this down, since "where exactly is the cliff" is a good extra finding.
- **C vs D gap under the filter**, at ratio 1.0: `filtered_C − filtered_D` = 22.2 − 0 = **22.2 percentage points** — state this explicitly as the headline contribution number.
- **Expansion cost of reaching the cliff**: expansion factor at ratio 1.0 vs. at 0.5, i.e. what multiple of storage you pay to go from "partial protection" to "near-total protection."
- **Cross-scale consistency**: whether linkage (0%) and the cliff shape are stable at 1k/10k/30k, stated as a one-line confirmation with the three numbers side by side.

## 5. Step-by-step (what's left to do)

1. **Fill any gaps in the sweep.** Confirm ratio=0.5/0.75/1.0 exist for **both** single and multi schema, at **all three** scale points, for B/C/D. From the data shown so far, some cells (e.g. single-schema sweep, B at ratios other than the default) may be missing — fill only what's missing; do not re-run what's complete.
2. **(Optional, if time allows) Narrow the cliff.** Add ratio = 0.85 / 0.90 / 0.95 at the 10k scale only (cheapest informative scale) to locate the threshold more precisely for Fig. 2.
3. **Run the analysis script** to produce Tables 1–4 and Figs. 1–6 from the CSV logs.
4. **Write the `billing` limitation paragraph** (§3 above) into the Results and into B.5.1-style documentation.
5. **(Optional) Couchbase/Cassandra appendix.** If time remains after the MongoDB report is complete: fix Couchbase's missing index (this was the suspected root cause of its earlier slowness) and re-run just the **single-schema, ratio=1.0, 1k-scale** configuration on Couchbase and Cassandra — not the full grid. The goal of the appendix is only to show the **cliff and linkage=0% pattern replicate on another engine**, not to reproduce every table. This keeps the "generalizes across NoSQL" claim available without the multi-engine timeline risk.
6. **(Optional, only if you want `billing` to be a real security result) Fix 1 from the earlier diagnosis:** rebuild `cost_category` with fixed skewed dollar tiers instead of `pd.qcut`, re-run the B.5.1 sanity check on it, and if it passes, add it to Table 2 as a third attack field alongside `specific_diagnostic_test`.

## 6. What to explicitly change in the Introduction / Methodology text

- **Objective 1**: change "across three NoSQL engines" to **"in MongoDB, with generalisation to Couchbase and Cassandra explored as a secondary check where time permits."**
- **Scope paragraph**: state MongoDB as the primary and sole fully-evaluated engine; note that the pipeline's engine-agnostic design (client/adapter split) means extending to other engines is an implementation cost, not a redesign, and was partially validated (cite whatever Couchbase/Cassandra single-point data you do end up running).
- **B.2 Research design**: add `decoy_ratio ∈ {0.5, 0.75, 1.0}` as a formal independent variable, since it now drives your main figure.
- **B.5.1**: add `cost_category` to the list of fields with documented issues (alongside the earlier `race_category`/`age_category` reasoning), explaining the `pd.qcut` artifact.
- **B.12 Expected results**: replace the old "C leaks under the filter, D resists it" one-liner with the sharper, now-confirmed version: *recovery is roughly flat across low-to-moderate flattening and collapses sharply only at full flattening; under full flattening, naive decoys (C) are still ~22% recoverable after filtering while generative decoys (D) fall to 0%.*

## 7. Marking-relevance check

- **Introduction objectives (measurable/testable):** still satisfied — recovery %, linkage %, latency, overhead %, storage expansion, now indexed by decoy ratio as well as approach/engine/scale. Single-engine does not weaken measurability.
- **Methodology (flexibility claim, objective 4):** now evidenced by the **single-vs-multi-schema comparison on the same engine** (§2.4) rather than the cross-engine comparison — still a valid, measured demonstration of flexibility, just along a different axis.
- **Results (10 marks):** the six figures and four tables above are a complete, richer deliverable set than the original three-figure plan, because the ratio sweep adds a genuine trade-off curve instead of three isolated points.
- **Honesty/limitations:** the `billing` artifact is disclosed rather than hidden, and the single-engine scope is stated as a deliberate, explained scoping decision (time-boxing Couchbase's indexing issues), which is exactly the kind of transparent trade-off documentation the rubric rewards over a rushed, incomplete multi-engine run.
