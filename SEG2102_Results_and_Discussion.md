# Results and Discussion (draft, plain-language)

> **Notes on this draft.** This follows the same overall shape as the sample report you shared
> (explain how each thing works, show real output, then discuss what it means) but is written
> the way we actually talk about it, not in dense academic language — you should be able to read
> this straight through and understand it. Where a figure or table isn't ready yet, there's a
> clearly marked placeholder telling you exactly what needs to go there. Swap in real screenshots
> wherever you have them; the plots we've already generated are noted with their file names so
> you can just drop them in.
>
> Everything below is written for **MongoDB**, since that's the engine we actually completed a
> full run on. Mentions of Couchbase/Cassandra are limited to short honesty notes, not full
> results, because we didn't finish those.

---

## 1. How each approach works, and what it actually looks like

Before we get into numbers, it helps to just look at the data itself. We built four ways of
storing the same records — we call them Approach A, B, C, and D — and each one changes what
someone looking at the database would actually see. So instead of jumping straight to charts,
we're going to walk through each approach one at a time, show a handful of real records from our
database in that state, and explain what changed and why.

To make the comparison easy, we picked one real lab test that shows up several times in our
data (`URINALYSIS WITH REFLEX CULTURE`, appearing 6–7 times in our 1,000-record sample) and we
follow that *same group of records* through all four approaches. That way, when you compare the
figures side by side, you're looking at the same underlying data every time — only the storage
approach changes.

### 1.1 Approach A — plaintext (the "do nothing" baseline)

This is simply storing the data as-is, with no protection at all. It's our control group — the
thing we compare everything else against.

**Figure 1a** (`approach_A_example.png`) shows six real records stored this way. Every column —
the patient code, the test name, the test category — is fully readable. Anyone with read access
to the database, or anyone who manages to peek at it, sees everything immediately. There's no
attack needed here; the data just tells you everything on its own.

We keep this approach in the study for one reason: it's our sanity check. If our attack can't
recover 100% of the data from a plaintext database, something is wrong with the attack itself,
not the protection. As we'll see in Section 4, that's exactly what we confirmed.

### 1.2 Approach B — deterministic encryption (what most "encrypted databases" actually do)

This is the common, practical approach: encrypt the sensitive value so it's no longer readable,
but do it in a way that's still queryable — the same plaintext value always turns into the same
encrypted "token." This is how a lot of real encrypted-database setups work in practice, because
it lets you still search the database (e.g. "find every row where this token equals that
token") without ever decrypting anything server-side.

The problem is that this doesn't hide as much as people think.

**Figure 1b** (`approach_B_example.png`) shows the same six records, now encrypted. The test
name and patient code are unreadable hex strings instead of plain text — good. But look closer:
**every single row has the exact same token** in the `specific_diagnostic_test` column. That's
because all six records happen to be the same real test, and deterministic encryption always
turns the same input into the same output. So even without decrypting anything, an outside
observer can see "these six records are definitely the same thing" — they just don't know *what*
that thing is yet. That gap is exactly what Section 4's attack exploits.

### 1.3 Approach C — naive decoys (padding, done the simple way)

Approach C starts from B (still deterministic encryption) and adds a twist: alongside the real
records, we insert **fake records** — decoys — that use the exact same token as the real ones.
The idea is to hide the true count: if a value really only appears 6 times but we pad it up to
look like 100, an outside observer counting tokens can no longer tell how common the real value
actually is.

The word "naive" matters here. In Approach C, each decoy's other fields (like which lab
department it belongs to) are picked independently and randomly — they don't have to make sense
together. That's cheap to generate, but it's also a weakness, which is the whole point of
comparing C against D.

**Figure 1c** (`approach_C_example.png`) shows this directly. The top half of the figure is
"before decoys" — just the 7 real records, already encrypted like Approach B. The bottom half is
"after decoys" — the same records, but now mixed in with a few decoy records (out of 106 total
generated for this one value, we show 3 for space). Every row, real or fake, has the identical
token, so from the server's point of view they're indistinguishable.

But we also show a column that the server *never* sees: whether each row's other fields actually
make sense together. The real records are all tagged `Microbiology` (correct for a urinalysis
test) and pass a plausibility check. The decoy records got a random, unrelated category
(`Chemistry`) attached, and **fail** that same check. This is the exact weakness an attacker can
exploit: even without knowing which records are decoys by design, they can guess which *look*
fake and filter them back out. Section 4 shows this attack in action, and Section 5 shows exactly
how much it recovers.

### 1.4 Approach D — generative decoys (our contribution)

Approach D is our actual solution, and it starts from the same idea as C — real records padded
with decoys sharing the same token — but fixes the weakness. Instead of picking each decoy's
other fields independently at random, we sample them **together**, based on what real
combinations actually look like in the data. So a decoy for a urinalysis test gets a
plausible-looking companion category, not a random mismatched one.

**Figure 1d** (`approach_D_example.png`) shows the identical structure to Figure 1c — same real
records, same number of decoys shown — but this time **every row passes the plausibility
check**, including the decoys. There is no visible difference between real and fake anymore, not
even to someone specifically looking for tells.

D also does two more things that B and C don't:

- **Different collections use different encryption keys.** So the same patient's code becomes a
  *different* token in the `patients` collection than in the `billing` collection. We cover why
  this matters in Section 5 (it's what stops cross-collection linking).
- **A secret formula decides which records are real and which are decoys.** This is the part
  that makes the whole scheme actually work in practice, and it's worth explaining properly.

#### The secret formula, in plain terms

Here's the problem D has to solve: once real and decoy records are mixed together and
indistinguishable, *someone* still needs to be able to tell them apart — otherwise the real user
querying their own database would get garbage results mixed in with the real ones. But that
someone can't be the server, because if the server can tell real from fake, so can an attacker
who compromises the server.

The answer is a small piece of math that only works if you hold a secret key. In general terms
(the way we'd describe it to another researcher who wants to use their own version of this):

- Every record — real or decoy — gets a number, `i = 0, 1, 2, 3, …`, just counting up.
- We run that number through a *keyed* scrambling function (specifically HMAC-SHA256, a
  standard cryptographic hash that needs a secret key to compute) to get:
  1. **The record's ID** — the value actually stored on the server, which looks like random
     hexadecimal noise either way.
  2. **A yes/no answer**: is this one a decoy?

The key thing is that *both* of those come from the same secret key. If you don't have the key,
the IDs and the yes/no answers both look like meaningless random noise — you genuinely cannot
tell them apart. If you *do* have the key, you can recompute the exact same yes/no answer
yourself, instantly, for every record.

**Our specific version** uses:

- `k` — a 32-byte secret key, generated once and never sent to the server. We actually use a
  *different* key per collection (so `patients` and `billing` don't share one), which is also
  what breaks the cross-collection linking mentioned above.
- `d` — a number that controls roughly how many decoys we add per real record. If a value needs
  a lot of padding (because it's rare and we're flattening it up to match a common value), `d` is
  set low so more of the generated IDs come out as decoys; if it needs little padding, `d` is set
  high.
- The formula itself: `is_decoy(i) = 1 if HMAC(k, "tag" + i) mod (d+1) == 0, else 0`.

> **[PLACEHOLDER — optional]:** if you want a dedicated formula figure here (general formula on
> top, our specific `k`/`d` values and a worked example underneath — e.g. `i = 0..9` with the
> resulting IDs and real/decoy labels shown two ways: "with the key" vs. "without the key"), we
> can generate one from the real `secret_id.py` code, the same way the other figures were built.
> Let me know if you'd like that as its own figure rather than the text description above.

The practical result: the client (the legitimate user) recomputes this formula on every record it
gets back from a query, keeps the ones marked "real," and quietly discards the ones marked
"decoy" — the user never even notices the decoys exist. An attacker who has broken into the
server has the IDs but not the key, so this filtering step is simply not available to them — the
best they can do is fall back to guessing based on how realistic each record *looks*, which is
exactly the plausibility check Section 4 measures.

---

## 2. Testing at three different sizes

We didn't just test our solution on one dataset size — we ran it at three different scales:
**1,000, 10,000, and 30,000 records**. Table/Figure 2a below (`concept_scale_comparison.png`)
shows exactly what each of these actually contains, computed from the real data (not estimated):

| Scale | % of full dataset | Distinct test names seen | Most common test's count |
|---|---|---|---|
| 1,000 | 0.12% | 98 | 113 (`MAGNESIUM`) |
| 10,000 | 1.21% | 199 | 1,210 (`BASIC METABOLIC PANEL...`) |
| 30,000 | 3.63% | 226 | 3,547 (`BASIC METABOLIC PANEL...`) |

All three are drawn the same way: a random sample, without replacement, from the same real
826,843-record dataset, using a fixed random seed. That last part matters — it means the sampling
is reproducible (anyone re-running our code gets the identical sample), and it means the three
scales aren't three different datasets, just three different-sized windows into the same one.

Why three, and why these three specifically:

- **1,000** is small and fast. It's what we used while building and debugging the pipeline —
  fast enough to re-run dozens of times an hour. The downside is that at this size, most test
  names only show up a handful of times, so some patterns are still a bit noisy.
- **10,000** is ten times bigger. This is where we started seeing patterns stabilize — the same
  test names repeat often enough that frequency-based patterns (and frequency-based attacks) show
  up clearly.
- **30,000** is our largest tested point. This is where the real costs of our solution — extra
  storage, extra query time — become clearly visible, and it's also where we ran our most
  complete set of experiments (every approach, every decoy ratio, both the single-collection and
  three-collection setup).

Running the same experiment at all three sizes lets us check something important: **does our
result hold up as the data gets bigger, or was it a fluke of a small sample?** As you'll see in
Section 5, the answer is yes — the security pattern is essentially identical at all three sizes.

> **[PLACEHOLDER]:** if you want a second figure here showing runtime/storage growth visually
> across the three scales (e.g. a simple bar chart of dataset size vs. total experiment time or
> vs. storage used), we can build one from `results/raw_results.csv` — let us know if that's a
> section you want to add.

---

## 3. How the attack actually works, and what it actually found

This is probably the most important section for convincing a reader that our security numbers
are real and not just made up — so we're going to walk through exactly what the attack sees, step
by step, using real output from our own code.

### 3.1 The value-recovery attack

Here's the situation the attack simulates: imagine someone has broken into the database server
(or is the database provider itself, being "honest but curious"). They can see every encrypted
record, and they can see every query that comes in — but not what the query means, and not what's
inside any encrypted field. All they can see is:

1. **Which token was queried.**
2. **How many records came back.**

That's it. No decryption, no key, nothing else — except one more thing: some general public
knowledge about how common different lab tests usually are (similar to how hospital statistics
about test frequency are published in general — nothing specific to our patients). The attack
uses that general knowledge to work out the answer.

The logic is: if a token comes back with, say, 950 records, and the attacker knows that in a
typical hospital dataset the *most common* test appears roughly that many times, then that token
probably *is* that test. This is called a frequency-matching attack, and specifically we use an
optimal-assignment version of it — instead of guessing token-by-token, it finds the single
best overall matching between all observed tokens and all candidate test names at once (using a
standard algorithm called the Hungarian algorithm), the same way you'd optimally assign delivery
drivers to delivery routes to minimize total distance.

**Figure 3a** (`concept_attack_value_output.png`) shows this attack's *actual, literal output* —
not a mock-up, this is what our code produced — for Approach B and Approach D side by side, at
full padding:

- **Approach B (left, red header):** every single row shown is correctly guessed. The attacker
  saw a token with 113 records and correctly guessed `MAGNESIUM`; saw 111 records and correctly
  guessed `BASIC METABOLIC PANEL`; and so on. **100% correct** on the rows shown.
- **Approach D (right, green header):** every row shows the exact same observed volume — 113 —
  because our decoys have flattened every value's count to look identical. With no volume
  difference left to go on, the attacker's guesses are essentially random noise: `LIVER PANEL`
  guessed for what was actually `LACTIC ACID, WHOLE BLOOD`; `POTASSIUM` guessed for what was
  actually `ARTERIAL BLOOD GAS`. **0% correct** on the rows shown.

This is the clearest possible demonstration that the defense isn't just "encrypt harder" — it's
specifically taking away the one signal (record count) that this style of attack depends on.

### 3.2 The linkage attack

The second attack asks a different question: even if you can't tell *what* a record says, can
you tell that two records in different tables belong to the *same person*? In a hospital
setting, being able to link a patient's billing record to their lab record — without knowing
either one's contents — can still leak sensitive information (for instance, that someone who was
billed for an expensive procedure also had a specific lab test done).

The attacker's only signal here is: does the same patient's encrypted ID token look identical in
both tables? If yes, they're linked. If the tokens differ, the attacker has no way to connect
them.

**Figure 3b** (`concept_attack_linkage_output.png`) shows this directly, for five real patients:

- **Under Approach B** (shared encryption key across every table): every patient's token is
  **byte-for-byte identical** in both the `patients` and `billing` tables. The attacker's verdict
  is `LINKED` for all five, every time. Measured across the whole dataset, this reaches **100%**
  linkage accuracy.
- **Under Approach D** (a different key per table): the same patient gets a **completely
  different** token in each table. The attacker's verdict is `not linked` for all five. Measured
  across the whole dataset, this drops to **0%**.

Put together, these two figures are the whole security story in miniature: Approach D doesn't
just make records harder to read — it removes the specific patterns (record counts, matching
IDs) that an attacker actually needs, and we can show, with real output, exactly how that
attack fails once those patterns are gone.

---

## 4. Security results

Now that we've shown how the attacks work, here's what they found across the full set of
experiments.

### 4.1 The headline result: a cliff, not a slope

We didn't just test one "amount" of padding — we tested three: pad each value up to 50%, 75%,
or 100% of the most common value's count (we call this the *decoy ratio*). The obvious
assumption going in was that more padding = gradually better protection. **That's not what we
found.**

| Decoy ratio | Approach B (reference) | Approach C, after filtering | Approach D, after filtering |
|---|---|---|---|
| 0.5 | 93.3% recoverable | 39.7% | 39.6% |
| 0.75 | 93.3% | 39.6% | 32.4% |
| **1.0 (full)** | 93.3% | **22.2%** | **0.0%** |

*(See `mongo_fig2_the_cliff.png` and `table2_recovery_vs_ratio.md` for the full figure/table.)*

Recovery stays roughly flat through 0.5 and 0.75 padding, and only drops sharply once padding
reaches 100% (every value flattened to look equally common). We're calling this "the cliff,"
because that's really what the shape looks like on a graph — not a gradual slope down, but a
sudden drop right at the end.

At that cliff point, the gap between naive decoys (Approach C) and our generative decoys
(Approach D) is the clearest it gets: **22.2 percentage points**. Once an attacker applies the
same plausibility check we showed in Section 1.3/1.4, naive decoys get filtered back out and
recovery climbs back up to 22.2%; generative decoys survive that same filter and recovery stays
at 0%. That 22.2-point gap is, in one number, the value our specific contribution (realistic
decoys, not just any decoys) actually adds.

### 4.2 Linkage security

As shown in Section 3.2, linkage recovery drops from 100% (Approaches A, B, and C all share one
key) to 0% (Approach D). We confirmed this holds at **all three scales** — 1,000, 10,000, and
30,000 records all show the identical 100% → 0% pattern (`table3_linkage_before_after.md`,
`mongo_fig4_linkage_before_after.png`). This tells us the linkage defense isn't a fluke of one
dataset size — it's a property of the *method* (different keys per collection), so it doesn't
degrade or improve as the data grows.

---

## 5. Cost — what we pay for this protection

Security never comes for free, so here's what Approach D actually costs, measured directly.

### 5.1 Query speed

| Scale | Approach A | Approach B | Approach D (full padding) |
|---|---|---|---|
| 1,000 | 1.55 ms | 1.56 ms (+0.4%) | 3.29 ms (+112%) |
| 10,000 | 3.29 ms | 3.31 ms (+0.5%) | 5.03 ms (+53%) |
| 30,000 | 6.49 ms | 6.68 ms (+3.0%) | 14.23 ms (+119%) |

*(`table1_before_after_performance.md`, `mongo_fig1_performance_before_after.png`)*

Two things stand out. First, Approach B (encryption alone, no decoys) is basically free — under
1% slower than plaintext at every scale. Second, Approach D roughly doubles query time compared
to plaintext. That's a real cost, but even at its slowest (30,000 records) a query still only
takes about 14 milliseconds — for a system protecting sensitive health data, that's a reasonable
price for the security gained.

### 5.2 Storage

This is where the cost is much more visible. To flatten every value up to the frequency of the
single most common one, rare values need a *lot* of padding.

| Decoy ratio | Storage multiple (vs. plaintext) |
|---|---|
| 0.5 | 41.1x |
| 0.75 | 61.5x |
| 1.0 (full) | 89.4x |

*(`table4_cost_vs_ratio.md`)*

Going from "partial protection" (ratio 0.5) to "full protection" (ratio 1.0) — the point where
recovery actually drops to 0% — costs roughly **2.18x more storage**. This is the real
trade-off: the padding level that actually works is also the most expensive one. We think that's
an honest and important thing to say plainly, rather than downplaying it — see Section 6 and
`mongo_fig3_security_cost_tradeoff.png` for the full picture of security vs. cost together.

---

## 6. Strengths and weaknesses

**Strengths:**
- The core result — full padding drops recovery to 0% while naive decoys only drop it to 22.2%
  under the same filter — held up consistently at all three scales we tested.
- The linkage defense (different key per collection) is simple, cheap, and completely effective
  in our tests (100% → 0%, at every scale).
- Query-time cost stays reasonable even at the largest scale and strongest protection level
  (about 14ms per query at 30,000 records).
- Every attack result in this report comes from running the actual attack code against actual
  stored data — nothing here is simulated or estimated by hand.

**Weaknesses:**
- The strong security result only shows up at *full* padding (ratio 1.0). At lower padding
  levels, our decoys don't protect much more than doing nothing, which means there's no "cheap
  middle ground" — you either pay the full storage cost or you don't get much benefit.
- Storage cost at full padding is steep (up to ~89x). For a real deployment, that's a serious
  practical constraint, especially for large sensitive fields.
- We haven't yet narrowed down exactly *where* between 75% and 100% padding the cliff begins —
  we know it's somewhere in that range, but not the precise point. (Testing at, say, 85% and 90%
  padding would answer this — noted as future work.)
- We only completed a full run on MongoDB. We built and tested adapters for Couchbase, Cassandra,
  and ArangoDB too, and confirmed the same pattern holds on at least two of them earlier in
  development, but we don't have a complete, up-to-date multi-engine comparison to report here.

---

## 7. Validation — making sure our results are actually real

Because this whole report depends on trusting that our attack results are genuine, it's worth
being upfront about how we checked our own work, including the mistakes we found and fixed along
the way — we think that's more convincing than pretending everything worked on the first try.

- **The plaintext sanity check.** Approach A must always show 100% recovery, since there's
  nothing to attack — the data's just sitting there in the clear. If it ever showed less than
  100%, that would mean our *attack code* was broken, not that plaintext is somehow "secure."
  It passed, every time, at every scale.
- **We found and fixed a bug where our own attack was cheating by accident.** Early on, when
  decoys fully flattened the record counts to identical values, our matching algorithm still
  produced suspiciously good guesses — not because it could actually tell records apart, but
  because of the *order* it happened to process them in, which quietly lined up with the answer.
  We fixed this by shuffling that order with a fixed random seed before matching, so the
  attacker genuinely has no leftover advantage once the counts are truly flattened. This is
  exactly the kind of thing we want to be transparent about, since it's the sort of subtle bug
  that could otherwise make a defense look worse (or an attack look better) than it really is.
- **We found and fixed a bug in decoy generation itself.** For rare values that needed a *lot*
  of padding, our first version quietly generated too few decoys, so full padding wasn't
  actually reaching the target we thought it was. Fixed by reworking how the padding amount is
  calculated.
- **We double-checked our numbers weren't corrupted by how we ran the experiments.** Some very
  long experiment runs had to be split into smaller chunks to avoid timeouts, and one of the
  numbers we compute (storage-expansion factor) was silently defaulting to a placeholder value
  in a few of those split runs. We caught this while double-checking Table 4 and fixed it by
  recomputing that number directly from real storage measurements instead of trusting a
  possibly-stale intermediate value.
- **Everything is re-runnable.** All of our numbers come from `results/raw_results.csv`, which
  is generated by running `run_experiment.py` against a live database, not hand-entered. We also
  keep a small automated regression test (`tests/test_leakage_contrast.py`) that checks the core
  claims — naive decoys are filterable, generative decoys aren't, Approach D beats Approach B —
  every time we change the code, so a future change can't silently break the headline result
  without us noticing.

We think this list matters as much as the results themselves: it shows the numbers in this
report were arrived at by actually running the system, hitting real problems, and fixing them —
not by writing down what we expected to see.

---

## 8. Summary

Putting it all together: Approach D (our generative-decoy solution) does what it's supposed to
do, but only once padding is pushed all the way to full flattening. At that point, value
recovery drops from 93% (plain encryption) to 0%, cross-collection linking drops from 100% to
0%, and — importantly — it survives the same plausibility check that strips naive decoys
(Approach C) back up to 22%. That protection costs roughly double the query time and up to ~89x
the storage of plaintext, and both of those costs held consistently as we scaled the dataset
from 1,000 to 30,000 records. Every one of these numbers comes from actually running attacks
against actually stored data, and we've documented the real bugs we found and fixed while
getting there, rather than presenting a cleaned-up version of events.

> **[PLACEHOLDER — sections you mentioned wanting to add later]:** slot new subsections in here
> as you get more images/results — e.g. a dedicated Couchbase/Cassandra appendix if you finish
> that, or a narrower cliff-threshold experiment (ratio 0.85/0.90/0.95) if you run it. Just say
> which section you're adding and we'll fit it into this same plain-language style.
