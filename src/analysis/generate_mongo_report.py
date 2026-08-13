"""Implements SEG2102_MongoDB_Only_Plan.md (Revision 3) section 3's exact deliverables,
from data already collected in results/raw_results.csv (MongoDB only, no new experiment
runs needed). Reuses styling/helpers from generate_report.py rather than duplicating them.

Usage:
    python -m src.analysis.generate_mongo_report

Produces:
    results/tables/table1_before_after_performance.md   Table 1 -- A/B/D latency/throughput/CPU per scale
    results/tables/table2_recovery_vs_ratio.md           Table 2 -- THE CLIFF, as a table
    results/tables/table3_linkage_before_after.md        Table 3 -- linkage, all 3 scales
    results/tables/table4_cost_vs_ratio.md                Table 4 -- storage expansion vs ratio
    results/tables/billing_supplementary.md               billing/cost_category, non-headline
    results/tables/mongo_derived_values.md                 the numeric findings for Discussion
    results/figures/mongo_fig1_performance_before_after.png
    results/figures/mongo_fig2_the_cliff.png               headline figure
    results/figures/mongo_fig3_security_cost_tradeoff.png
    results/figures/mongo_fig4_linkage_before_after.png
    results/figures/fig5_data_view.png                     (= generate_report's fig4_data_view, renamed per this plan)
    results/figures/mongo_fig6_metadata_view.png
"""
from __future__ import annotations

import os
import shutil

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

from src.core import config, decoys, encryption
from src.analysis.generate_report import (
    APPROACH_COLOR,
    APPROACH_LABEL,
    FIG_DIR,
    GRID,
    INK,
    MUTED,
    SURFACE,
    TABLE_DIR,
    _style_axes,
    load_results,
    plot_fig4_data_view,
)

SCALES = [1_000, 10_000, 30_000]
RATIOS = [0.5, 0.75, 1.0]
HEADLINE_SCALE = 30_000


def _write(lines: list[str], filename: str) -> None:
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _single_lab_orders(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["schema"] == "single") & (df["collection"] == "lab_orders")]


def _multi(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["schema"] == "multi"]


# ---------------------------------------------------------------------------
# Table 1 -- Before/after performance on lab_orders (plan section 2.1 / 3)
# ---------------------------------------------------------------------------

def write_table1_before_after_performance(df: pd.DataFrame) -> pd.DataFrame:
    single = _single_lab_orders(df)
    rows = []
    for scale in SCALES:
        a = single[(single["scale"] == scale) & (single["approach"] == "A")]
        a_lat = a["mean_latency_ms"].mean()
        for label, sub in [
            ("A", single[(single["scale"] == scale) & (single["approach"] == "A")]),
            ("B", single[(single["scale"] == scale) & (single["approach"] == "B")]),
            ("C (ratio=1.0)", single[(single["scale"] == scale) & (single["approach"] == "C") & (single["decoy_target_ratio"] == 1.0)]),
            ("D (ratio=1.0)", single[(single["scale"] == scale) & (single["approach"] == "D") & (single["decoy_target_ratio"] == 1.0)]),
        ]:
            m = sub["mean_latency_ms"].mean()
            overhead = (m - a_lat) / a_lat * 100 if a_lat else 0.0
            rows.append(
                {
                    "scale": scale,
                    "approach": label,
                    "mean_latency_ms": m,
                    "p95_latency_ms": sub["p95_latency_ms"].mean(),
                    "throughput_qps": sub["throughput_qps"].mean(),
                    "cpu_percent": sub["cpu_percent"].mean(),
                    "overhead_vs_A_pct": overhead,
                }
            )
    out = pd.DataFrame(rows)

    lines = [
        "# Table 1 — Before/after performance on lab_orders (A -> B -> C -> D)\n",
        "_C and D are both shown at decoy_target_ratio=1.0, the operating point that actually "
        "collapses D's recovery to 0% (Table 2), so this is the cost of the protection level "
        "that works, not an arbitrary point on the sweep -- and it isolates the extra cost D "
        "pays over C for the same amount of padding (generative vs. naive decoy generation)._\n",
    ]
    cols = ["scale", "approach", "mean_latency_ms", "p95_latency_ms", "throughput_qps", "cpu_percent", "overhead_vs_A_pct"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, r in out.iterrows():
        lines.append(
            f"| {int(r['scale']):,} | {r['approach']} | {r['mean_latency_ms']:.3f} | {r['p95_latency_ms']:.3f} | "
            f"{r['throughput_qps']:.1f} | {r['cpu_percent']:.1f} | {r['overhead_vs_A_pct']:+.1f}% |"
        )
    _write(lines, "table1_before_after_performance.md")
    return out


def plot_fig1_performance_before_after(table1: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    label_color = {
        "A": APPROACH_COLOR["A"],
        "B": APPROACH_COLOR["B"],
        "C (ratio=1.0)": APPROACH_COLOR["C"],
        "D (ratio=1.0)": APPROACH_COLOR["D"],
    }
    legend_label = {"A": "A", "B": "B", "C (ratio=1.0)": "C", "D (ratio=1.0)": "D"}
    for label in ["A", "B", "C (ratio=1.0)", "D (ratio=1.0)"]:
        s = table1[table1["approach"] == label].sort_values("scale")
        ax.plot(s["scale"], s["mean_latency_ms"], marker="o", markersize=7, linewidth=2, color=label_color[label], label=legend_label[label])
    ax.set_xscale("log")
    ax.set_xlabel("Dataset scale (records)", color=MUTED)
    ax.set_ylabel("Mean query latency (ms)", color=MUTED)
    ax.legend(frameon=False)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "mongo_fig1_performance_before_after.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Table 2 -- Value-recovery vs. decoy ratio == THE CLIFF (plan section 2.2 / 3)
# ---------------------------------------------------------------------------

def write_table2_recovery_vs_ratio(df: pd.DataFrame, scale: int = HEADLINE_SCALE) -> pd.DataFrame:
    single = _single_lab_orders(df)
    a_recovery = single[(single["scale"] == scale) & (single["approach"] == "A")]["recovery_accuracy"].mean()
    b_recovery = single[(single["scale"] == scale) & (single["approach"] == "B")]["recovery_accuracy"].mean()
    rows = []
    for ratio in RATIOS:
        c = single[(single["scale"] == scale) & (single["approach"] == "C") & (single["decoy_target_ratio"] == ratio)]
        d = single[(single["scale"] == scale) & (single["approach"] == "D") & (single["decoy_target_ratio"] == ratio)]
        rows.append(
            {
                "ratio": ratio,
                "A": a_recovery,
                "B": b_recovery,
                "C_unfiltered": c["recovery_accuracy"].mean(),
                "C_filtered": c["recovery_accuracy_filtered"].mean(),
                "D_unfiltered": d["recovery_accuracy"].mean(),
                "D_filtered": d["recovery_accuracy_filtered"].mean(),
            }
        )
    out = pd.DataFrame(rows)

    lines = [
        f"# Table 2 — Value-recovery vs. decoy ratio (lab_orders, scale = {scale:,}) — THE CLIFF\n",
        "_A and B have no decoy ratio; shown as flat reference rows (A = plaintext sanity check, "
        "~100%; B = deterministic encryption, no decoys). Recovery does not fall gradually "
        "with ratio -- it stays roughly flat at 0.5-0.75, then collapses only at full flattening "
        "(ratio=1.0). This is the single strongest security result in this study._\n",
    ]
    lines.append("| ratio | A | B | C (unfiltered) | C (filtered) | D (unfiltered) | D (filtered) |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in out.iterrows():
        lines.append(
            f"| {r['ratio']} | {r['A']:.1%} | {r['B']:.1%} | {r['C_unfiltered']:.1%} | {r['C_filtered']:.1%} | "
            f"{r['D_unfiltered']:.1%} | {r['D_filtered']:.1%} |"
        )
    _write(lines, "table2_recovery_vs_ratio.md")
    return out


def plot_fig2_the_cliff(table2: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    x = table2["ratio"]
    ax.axhline(table2["A"].iloc[0], color=APPROACH_COLOR["A"], linestyle=":", linewidth=1.5, label="A (plaintext, sanity check)")
    ax.axhline(table2["B"].iloc[0], color=APPROACH_COLOR["B"], linestyle="--", linewidth=1.5, label="B (no decoys, reference)")
    ax.plot(x, table2["C_filtered"], marker="D", markersize=8, linewidth=2.5, color=APPROACH_COLOR["C"], label="C — filtered (naive decoys)")
    ax.plot(x, table2["D_filtered"], marker="^", markersize=9, linewidth=2.5, color=APPROACH_COLOR["D"], label="D — filtered (generative decoys, ours)")
    ax.set_xticks(RATIOS)
    ax.set_xlabel("decoy_target_ratio", color=MUTED)
    ax.set_ylabel("Attacker query-recovery accuracy", color=MUTED)
    ax.set_ylim(-0.05, 1.05)
    # A and B both sit near the top of the plot (~0.93-1.0), so any in-plot legend location
    # overlaps one of them -- place it below the axes instead.
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=9)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "mongo_fig2_the_cliff.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Table 3 -- Linkage recovery, before vs. after, all 3 scales (plan section 2.2 / 3)
# ---------------------------------------------------------------------------

def write_table3_linkage_before_after(df: pd.DataFrame) -> pd.DataFrame:
    link = _multi(df)
    link = link[link["collection"] == "linkage"]

    lines = ["# Table 3 — Cross-collection linkage recovery, before (A/B/C) vs. after (D)\n"]
    lines.append("| scale | A | B | C | D |")
    lines.append("|---|---|---|---|---|")
    vals_by_scale = {}
    for scale in SCALES:
        sub = link[link["scale"] == scale]
        vals = {a: (sub[sub["approach"] == a]["linkage_recovery_accuracy"].iloc[0] if not sub[sub["approach"] == a].empty else None) for a in "ABCD"}
        vals_by_scale[scale] = vals
        lines.append(f"| {scale:,} | " + " | ".join(f"{vals[a]:.1%}" if vals[a] is not None else "-" for a in "ABCD") + " |")
    lines.append(
        "\n_Consistent across all three scale points: A/B/C stay at 100% (shared key -> "
        "trivially linkable), D stays at 0% (per-collection keys -> unlinkable). Scale-independent._\n"
    )
    _write(lines, "table3_linkage_before_after.md")
    return pd.DataFrame(
        [{"scale": s, **v} for s, v in vals_by_scale.items()]
    )


def plot_fig4_linkage_before_after(linkage_table: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    approaches = list("ABCD")
    width = 0.8 / len(approaches)
    x = np.arange(len(SCALES))
    for i, a in enumerate(approaches):
        vals = [linkage_table[linkage_table["scale"] == s][a].iloc[0] for s in SCALES]
        offset = (i - (len(approaches) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width=width, color=APPROACH_COLOR[a], label=APPROACH_LABEL[a])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.0%}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s:,}" for s in SCALES], color=INK)
    ax.set_xlabel("Dataset scale (records)", color=MUTED)
    ax.set_ylabel("Linkage-recovery accuracy", color=MUTED)
    ax.set_ylim(top=1.15)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=4, fontsize=8)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "mongo_fig4_linkage_before_after.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Table 4 -- Cost: storage expansion vs. decoy ratio (plan section 2.3 / 3)
# ---------------------------------------------------------------------------

def write_table4_cost_vs_ratio(df: pd.DataFrame, scale: int = HEADLINE_SCALE) -> pd.DataFrame:
    multi = _multi(df)
    rows = []
    lines = [f"# Table 4 — Cost: storage-expansion factor vs. decoy ratio (scale = {scale:,})\n"]
    lines.append(
        "_expansion_factor is recomputed here as storage_mb / A's storage_mb for the same "
        "collection/scale, rather than trusting the stored `ciphertext_expansion_factor` "
        "column: several rows were logged by a process invocation that only ran approach C "
        "or D (split off to survive background-job interruptions) and never saw approach A, "
        "so that column silently defaulted to 1.0x for those rows -- recomputing it here "
        "from the actual storage figures avoids reporting that placeholder as data._\n"
    )
    lines.append("| collection | approach | ratio | storage_mb | expansion_factor |")
    lines.append("|---|---|---|---|---|")
    for coll in ["lab_orders", "patients"]:
        a_storage = multi[(multi["scale"] == scale) & (multi["collection"] == coll) & (multi["approach"] == "A")]["storage_mb"].mean()
        for approach in ["C", "D"]:
            for ratio in RATIOS:
                sub = multi[
                    (multi["scale"] == scale) & (multi["collection"] == coll)
                    & (multi["approach"] == approach) & (multi["decoy_target_ratio"] == ratio)
                ]
                if sub.empty:
                    continue
                storage = sub["storage_mb"].mean()
                expansion = storage / a_storage if a_storage else float("nan")
                rows.append({"collection": coll, "approach": approach, "ratio": ratio, "storage_mb": storage, "expansion_factor": expansion})
                lines.append(f"| {coll} | {approach} | {ratio} | {storage:.2f} | {expansion:.2f}x |")
    _write(lines, "table4_cost_vs_ratio.md")
    return pd.DataFrame(rows)


def plot_fig3_security_cost_tradeoff(table2: pd.DataFrame, table4: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    lo4 = table4[table4["collection"] == "lab_orders"]
    for approach, marker in [("C", "D"), ("D", "^")]:
        sub = lo4[lo4["approach"] == approach]
        for _, row in sub.iterrows():
            t2 = table2[table2["ratio"] == row["ratio"]]
            recovery = t2[f"{approach}_filtered"].iloc[0] if not t2.empty else None
            if recovery is None:
                continue
            ax.scatter(row["expansion_factor"], recovery, s=160, color=APPROACH_COLOR[approach], marker=marker, edgecolors=SURFACE, linewidths=1.5, zorder=3)
            ax.annotate(f"{approach}-{row['ratio']}", (row["expansion_factor"], recovery), textcoords="offset points", xytext=(8, 6), fontsize=8, color=MUTED)
    ax.set_xlabel("Storage-expansion factor (x, lab_orders)", color=MUTED)
    ax.set_ylabel("Recovery accuracy (filtered)", color=MUTED)
    ax.set_ylim(bottom=-0.05)

    from matplotlib.lines import Line2D

    handles = [
        Line2D([0], [0], marker="D", color="none", markerfacecolor=APPROACH_COLOR["C"], markersize=10, label="C — naive decoys (each point = one decoy_target_ratio)"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor=APPROACH_COLOR["D"], markersize=11, label="D — generative decoys, ours (each point = one decoy_target_ratio)"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), fontsize=9)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "mongo_fig3_security_cost_tradeoff.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# billing/cost_category -- supplementary, non-headline (plan section 3 footer)
# ---------------------------------------------------------------------------

def write_billing_supplementary(df: pd.DataFrame, scale: int = HEADLINE_SCALE) -> None:
    multi = _multi(df)
    billing = multi[(multi["collection"] == "billing") & (multi["scale"] == scale)]

    lines = ["# Supplementary — billing/cost_category (not a headline security result)\n"]
    lines.append(
        "_Note: this plan's original text describes `cost_category` as built with `pd.qcut` "
        "(uniform quantile bins), producing a construction artifact with no real skew. That has "
        "since been fixed in code -- `cost_category` is now built with fixed dollar-threshold "
        "tiers (`pd.cut`), which carries genuine skew from the underlying test-cost distribution, "
        "and the numbers below do move with the decoy ratio (100% -> 46.5%), unlike the old "
        "uniform-bin artifact. It is still kept out of the headline Table 2, however: at only 4 "
        "candidate values it remains lower-cardinality than the B.5.1-vetted "
        "`specific_diagnostic_test`, so its recovery floor is structurally higher and its role "
        "here is to show the solution behaves reasonably on a secondary field, not to replace "
        "the headline cliff._\n"
    )
    lines.append("| approach | ratio | recovery | filtered |")
    lines.append("|---|---|---|---|")
    for _, row in billing.sort_values(["approach", "decoy_target_ratio"]).iterrows():
        ratio = row["decoy_target_ratio"] if pd.notna(row["decoy_target_ratio"]) else "-"
        filt = f"{row['recovery_accuracy_filtered']:.1%}" if pd.notna(row["recovery_accuracy_filtered"]) else "-"
        lines.append(f"| {row['approach']} | {ratio} | {row['recovery_accuracy']:.1%} | {filt} |")
    _write(lines, "billing_supplementary.md")


# ---------------------------------------------------------------------------
# Fig. 5 -- before/after DATA view (reuse generate_report's existing figure)
# ---------------------------------------------------------------------------

def make_fig5_data_view() -> None:
    plot_fig4_data_view()  # writes results/figures/fig4_data_view.png
    src = os.path.join(FIG_DIR, "fig4_data_view.png")
    dst = os.path.join(FIG_DIR, "fig5_data_view.png")
    if os.path.exists(src):
        shutil.copyfile(src, dst)


# ---------------------------------------------------------------------------
# Fig. 6 -- before/after METADATA view: ratio 0.5 vs. ratio 1.0
# ---------------------------------------------------------------------------

def plot_fig6_metadata_view() -> None:
    from src.core import dataset, schema

    df, _ = dataset.load_scaled_dataset(min(10_000, dataset.full_dataset_size()))
    lab_orders = schema.build_lab_orders(df)
    value_counts = lab_orders[config.SENSITIVE_FIELD].astype(str).value_counts()
    after_05 = pd.Series(
        {v: value_counts[v] + decoys.compute_target_counts(value_counts.to_dict(), target_ratio=0.5).get(v, 0) for v in value_counts.index}
    )
    after_10 = pd.Series(
        {v: value_counts[v] + decoys.compute_target_counts(value_counts.to_dict(), target_ratio=1.0).get(v, 0) for v in value_counts.index}
    )
    top_values = value_counts.head(15).index

    fig, axes = plt.subplots(1, 2, figsize=(15, 9.5), gridspec_kw={"width_ratios": [1.6, 1]})

    ax_hist = axes[0]
    x = np.arange(len(top_values))
    width = 0.27
    ax_hist.bar(x - width, value_counts[top_values], width=width, color=APPROACH_COLOR["B"], label="raw (no decoys)")
    ax_hist.bar(x, after_05[top_values], width=width, color="#c9a227", label="ratio=0.5")
    ax_hist.bar(x + width, after_10[top_values], width=width, color=APPROACH_COLOR["D"], label="ratio=1.0 (flat)")
    ax_hist.set_xticks(x)
    ax_hist.set_xticklabels(top_values, rotation=60, ha="right", fontsize=7, color=INK)
    ax_hist.set_ylabel("Observed record count", color=MUTED)
    _style_axes(ax_hist)
    # The ratio=1.0 bars are flat and tall across the whole chart (that's the point -- full
    # flattening), so there's no open space inside the axes for a legend, and the rotated
    # x-tick labels already use the space directly below the axes. A *figure*-level legend
    # (placed in figure coordinates, well below both the labels and panel (b)'s independent
    # text block) avoids both, and avoids shrinking either axes' box via tight_layout/rect
    # (which previously squeezed panel (b)'s fixed-fraction text into itself).
    handles, labels = ax_hist.get_legend_handles_labels()

    ax_link = axes[1]
    ax_link.axis("off")
    sample_code = str(lab_orders.iloc[0][config.LINK_FIELD])
    b_key = encryption.derive_token_key(None)
    tok_patients_b = encryption.deterministic_token(sample_code, key=b_key).hex()[:12]
    tok_billing_b = tok_patients_b
    tok_patients_d = encryption.deterministic_token(sample_code, key=encryption.derive_token_key("patients")).hex()[:12]
    tok_billing_d = encryption.deterministic_token(sample_code, key=encryption.derive_token_key("billing")).hex()[:12]
    ax_link.text(0.0, 0.85, f"patient_code = {sample_code}", fontsize=9, family="monospace", color=INK)
    ax_link.text(
        0.0, 0.60,
        f"Before (B/C, shared key):\n  patients token = {tok_patients_b}...\n  billing  token = {tok_billing_b}...\n  (equal -> linkable)",
        fontsize=8.5, family="monospace", color="#c1352b",
    )
    ax_link.text(
        0.0, 0.20,
        f"After (D, per-collection keys):\n  patients token = {tok_patients_d}...\n  billing  token = {tok_billing_d}...\n  (different -> not linkable)",
        fontsize=8.5, family="monospace", color=APPROACH_COLOR["D"],
    )

    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.98, bottom=0.42, wspace=0.25)
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.31, 0.02), ncol=3, frameon=False, fontsize=9)
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "mongo_fig6_metadata_view.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Derived values (plan section 4)
# ---------------------------------------------------------------------------

def write_derived_values(df: pd.DataFrame, table1: pd.DataFrame, table2: pd.DataFrame, table4: pd.DataFrame, linkage_table: pd.DataFrame) -> None:
    lines = ["# Derived values (feeds the Discussion)\n"]

    lines.append("## Overhead of D (ratio=1.0) vs. A, per scale\n")
    lines.append("| scale | overhead |")
    lines.append("|---|---|")
    for scale in SCALES:
        row = table1[(table1["scale"] == scale) & (table1["approach"] == "D (ratio=1.0)")]
        lines.append(f"| {scale:,} | {row['overhead_vs_A_pct'].iloc[0]:+.1f}% |")

    lines.append("\n## B -> D recovery drop, per ratio (percentage points)\n")
    lines.append("| ratio | B | D (filtered) | drop (pp) |")
    lines.append("|---|---|---|---|")
    for _, r in table2.iterrows():
        drop = (r["B"] - r["D_filtered"]) * 100
        lines.append(f"| {r['ratio']} | {r['B']:.1%} | {r['D_filtered']:.1%} | {drop:.1f} |")

    r1 = table2[table2["ratio"] == 1.0].iloc[0]
    r075 = table2[table2["ratio"] == 0.75].iloc[0]
    lines.append("\n## Cliff threshold\n")
    lines.append(
        f"D (filtered) recovery is {r075['D_filtered']:.1%} at ratio=0.75 and {r1['D_filtered']:.1%} at ratio=1.0 -- "
        "the cliff falls somewhere in (0.75, 1.0]. Not narrowed further in this pass (would need "
        "ratio=0.85/0.90/0.95 runs, listed as optional future work in the plan); reported as a "
        "bounded interval, not a guessed point.\n"
    )

    gap = (r1["C_filtered"] - r1["D_filtered"]) * 100
    lines.append("## C vs. D gap under the realism filter, at ratio=1.0 (headline contribution number)\n")
    lines.append(f"filtered_C - filtered_D = {r1['C_filtered']:.1%} - {r1['D_filtered']:.1%} = **{gap:.1f} percentage points**\n")

    lo4 = table4[table4["collection"] == "lab_orders"]
    d_05 = lo4[(lo4["approach"] == "D") & (lo4["ratio"] == 0.5)]
    d_10 = lo4[(lo4["approach"] == "D") & (lo4["ratio"] == 1.0)]
    lines.append("## Expansion cost of reaching the cliff (lab_orders, D)\n")
    if not d_05.empty and not d_10.empty:
        e05, e10 = d_05["expansion_factor"].iloc[0], d_10["expansion_factor"].iloc[0]
        lines.append(f"Expansion at ratio=0.5: {e05:.2f}x. Expansion at ratio=1.0: {e10:.2f}x. "
                      f"Multiple paid to go from partial to near-total protection: {e10 / e05:.2f}x.\n")

    lines.append("## Cross-scale consistency\n")
    lines.append("Linkage recovery (A/B/C vs. D), all three scales:\n")
    lines.append("| scale | A | B | C | D |")
    lines.append("|---|---|---|---|---|")
    for _, row in linkage_table.iterrows():
        lines.append(f"| {int(row['scale']):,} | {row['A']:.1%} | {row['B']:.1%} | {row['C']:.1%} | {row['D']:.1%} |")
    lines.append("\nStable at 100%/100%/100%/0% across all three scales -- the linkage defence is scale-independent.\n")

    _write(lines, "mongo_derived_values.md")


def main():
    df = load_results()
    df = df[df["engine"] == "mongo"]

    table1 = write_table1_before_after_performance(df)
    plot_fig1_performance_before_after(table1)

    table2 = write_table2_recovery_vs_ratio(df)
    plot_fig2_the_cliff(table2)

    linkage_table = write_table3_linkage_before_after(df)
    plot_fig4_linkage_before_after(linkage_table)

    table4 = write_table4_cost_vs_ratio(df)
    plot_fig3_security_cost_tradeoff(table2, table4)

    write_billing_supplementary(df)

    make_fig5_data_view()
    plot_fig6_metadata_view()

    write_derived_values(df, table1, table2, table4, linkage_table)

    print(f"Wrote tables to {TABLE_DIR}/ and figures to {FIG_DIR}/")


if __name__ == "__main__":
    main()
