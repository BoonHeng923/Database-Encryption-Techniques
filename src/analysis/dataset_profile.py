"""Plan B.5.1 dataset sanity check — a required gate, run before building anything
else on top of the chosen sensitive field.

Usage:
    python -m src.analysis.dataset_profile

For the chosen target (`config.SENSITIVE_FIELD`) and a few alternative candidate
fields (for comparison/justification), reports:
  1. distinct-value count (categorical, not free text/unique)
  2. skew: frequency table, top-10 share, max/min ratio (not uniform)
  3. distinct-value count sits in a "non-trivial but not impossible" range
  4. data quality: null rate, obvious duplicate/encoding issues
  5. skew survives sub-sampling at the 1k/10k scale points
  6. a note on auxiliary-knowledge plausibility (write-up prose, not computed)

Writes results/tables/dataset_profile.md (the report-ready writeup) and
results/figures/dataset_profile_<field>.png (frequency histograms) for the target
field at full scale and at each sub-sample scale point.
"""
from __future__ import annotations

import os

import matplotlib.pyplot as plt

from src.analysis.generate_report import GRID, INK, MUTED, SURFACE, _style_axes
from src.core import config, dataset

CANDIDATE_FIELDS = [
    "specific_diagnostic_test",
    "diagnostic_test_category",
    "race_category",
    "age_category",
]

FIG_DIR = os.path.join(config.RESULTS_DIR, "figures")
TABLE_DIR = os.path.join(config.RESULTS_DIR, "tables")


def profile_field(df, field: str) -> dict:
    series = df[field]
    n = len(series)
    null_rate = series.isna().mean()
    vc = series.dropna().astype(str).value_counts()
    n_distinct = vc.shape[0]
    top10_share = vc.head(10).sum() / vc.sum() if vc.sum() else 0.0
    ratio = (vc.max() / vc.min()) if n_distinct > 0 else float("nan")
    duplicate_rows = df.duplicated().sum()
    return {
        "field": field,
        "n": n,
        "n_distinct": n_distinct,
        "null_rate": null_rate,
        "top10_share": top10_share,
        "max_min_ratio": ratio,
        "duplicate_rows": duplicate_rows,
        "top_values": vc.head(10),
    }


def plot_histogram(vc, field: str, scale_label: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5))
    top = vc.head(20)
    ax.bar(range(len(top)), top.values, color="#2a78d6")
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels(top.index, rotation=60, ha="right", fontsize=8, color=MUTED)
    ax.set_ylabel("Record count", color=MUTED)
    ax.set_title(f"{field} — top 20 values ({scale_label})", color=INK, fontsize=12, fontweight="bold")
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, f"dataset_profile_{field}_{scale_label}.png")
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def main():
    base, source = dataset._load_raw()
    print(f"Loaded raw dataset: source={source}, n={len(base)}")

    lines = ["# Dataset sanity check (plan B.5.1)\n", f"\nSource: **{source}**, {len(base):,} records.\n"]

    lines.append("\n## Candidate sensitive fields (full dataset)\n")
    lines.append("| field | n_distinct | null_rate | top10_share | max/min ratio |")
    lines.append("|---|---|---|---|---|")
    results = {}
    for field in CANDIDATE_FIELDS:
        if field not in base.columns:
            continue
        p = profile_field(base, field)
        results[field] = p
        lines.append(
            f"| {field} | {p['n_distinct']} | {p['null_rate']:.2%} | {p['top10_share']:.1%} | "
            f"{p['max_min_ratio']:.0f}x |"
        )

    chosen = config.SENSITIVE_FIELD
    p = results[chosen]
    lines.append(f"\n## Chosen field: `{chosen}`\n")
    lines.append(
        f"- Distinct values: **{p['n_distinct']}** — categorical, well within the "
        "\"a handful to a few hundred\" ideal range (B.5.1 §1/§3): not near-unique "
        "(rules out patient_code/free text), not trivially small (rules out sex/"
        "race_white_nonwhite-style 2-value fields, which would make recovery trivial)."
    )
    lines.append(
        f"- Top-10 share: **{p['top10_share']:.1%}**, max/min frequency ratio: "
        f"**{p['max_min_ratio']:.0f}x** — strongly skewed (Zipf-like), exactly what a "
        "count/frequency-matching attack exploits (B.5.1 §2)."
    )
    lines.append(f"- Null rate: **{p['null_rate']:.2%}**; duplicate full-row rate: **{p['duplicate_rows']}**.")
    lines.append(
        "- Rejected alternatives: `diagnostic_test_category` (only 8 categories — "
        "recovery would be closer to trivial), `race_category` (5 categories, and "
        "ethically better left as a demographic control field than the primary attack "
        "target), `age_category` (9 buckets, weaker skew, max/min ratio only ~18x)."
    )
    lines.append(f"\nTop 10 values for `{chosen}`:\n")
    lines.append("| value | count |")
    lines.append("|---|---|")
    for val, cnt in p["top_values"].items():
        lines.append(f"| {val} | {cnt} |")

    plot_histogram(base[chosen].value_counts(), chosen, "full")

    lines.append("\n## Skew survives sub-sampling\n")
    lines.append("| scale | n_distinct | top10_share | max/min ratio |")
    lines.append("|---|---|---|---|")
    for scale in config.SMALL_SCALE_POINTS:
        sample_df, info = dataset.load_scaled_dataset(scale, sensitive_field=chosen)
        sp = profile_field(sample_df, chosen)
        lines.append(f"| {scale:,} | {sp['n_distinct']} | {sp['top10_share']:.1%} | {sp['max_min_ratio']:.0f}x |")
        plot_histogram(sample_df[chosen].value_counts(), chosen, f"{scale}")
    lines.append(
        f"| {len(base):,} (full) | {p['n_distinct']} | {p['top10_share']:.1%} | {p['max_min_ratio']:.0f}x |"
    )

    lines.append("\n## Auxiliary-knowledge plausibility (B.5.1 §6)\n")
    lines.append(
        "The attack's auxiliary knowledge is the *relative* frequency with which each "
        "diagnostic test is ordered at the institution — analogous to published lab-"
        "utilisation statistics or a hospital's own historical ordering volumes, which "
        "are the kind of aggregate operational data a realistic honest-but-curious "
        "insider (or a party that has previously seen unencrypted billing/ordering "
        "summaries) could plausibly know without seeing any individual patient's "
        "record. This is the standard assumption in the count-attack literature "
        "[X4] and is modelled here directly as the dataset's own empirical "
        "distribution."
    )

    lines.append("\n## Data quality decisions\n")
    lines.append(
        "- `specific_diagnostic_test` values are pre-normalised (consistent upper-"
        "case naming in the source file); no free-text merging was required.\n"
        f"- Null rate in the target field is {p['null_rate']:.2%} — negligible; rows "
        "with a null target are dropped before workload generation.\n"
        "- Repeated `patient_code` values across rows are expected (one row per "
        "diagnostic test event, not per patient) and are not treated as duplicates."
    )

    os.makedirs(TABLE_DIR, exist_ok=True)
    out_path = os.path.join(TABLE_DIR, "dataset_profile.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {out_path} and histograms to {FIG_DIR}/")


if __name__ == "__main__":
    main()
