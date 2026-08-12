"""Builds the Results-section tables and figures from results/raw_results.csv.

Usage:
    python -m src.analysis.generate_report

Produces the named deliverables from plan B.8:
    results/tables/table1_performance.md     Table 1 — performance per approach x engine (largest scale, single schema)
    results/tables/table2_recovery.md        Table 2 — value-recovery accuracy per approach x engine
    results/tables/table3_linkage.md         Table 3 — cross-collection linkage-recovery accuracy, B vs D
    results/tables/derived_values.md         overhead %, expansion factor, B->D / C->D drops, cross-engine range, ...
    results/tables/summary.md/.csv           full per-scale summary (all scales, all metrics)
    results/tables/table2b_percollection_diagnostics.md   supplementary, NOT part of the headline
                                              Table 2 -- see note below
    results/tables/table_ratio_sweep.md      decoy_target_ratio as an independent variable (security vs. storage)
    results/figures/fig1_latency_vs_scale.png
    results/figures/fig2_recovery_accuracy.png
    results/figures/fig3_tradeoff_scatter.png
    results/figures/fig4_data_view.png       before/after DATA view (A/B/D, one example record)
    results/figures/fig5_metadata_view.png   before/after METADATA view (histogram, linkage, name tokenisation)
    results/figures/fig6_ratio_sweep.png     recovery (filtered) vs. storage as decoy_target_ratio varies
    results/figures/storage_expansion.png    (bonus, not a named B.8 deliverable)

Scope note (plan B.6/B.7): the only official value-recovery attack target is
`specific_diagnostic_test` on `lab_orders` -- Table 2 / Fig. 2 / Fig. 3 / derived_values.md
are built exclusively from schema="single" rows, which are always that collection, so
they already reflect this correctly. `patients`/`billing` also get a value-recovery
number in multi-schema runs (their own QUERY_FIELD), but per the plan's own B.5.1 sanity
check -- which rejected low-cardinality/weakly-skewed fields as attack targets, and
`race_category`/the old `cost_category` are exactly that kind of field -- those numbers
are reported separately in Table 2b as supplementary diagnostics, not folded into Table 2.
"""
from __future__ import annotations

import os

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

from src.core import config, dataset, decoys, encryption, metrics, schema

APPROACHES = ["A", "B", "C", "D"]
APPROACH_COLOR = {"A": "#2a78d6", "B": "#eb6834", "C": "#c9a227", "D": "#1baf7a"}
APPROACH_LABEL = {
    "A": "A — Plaintext",
    "B": "B — Deterministic (leaks)",
    "C": "C — Naive decoys",
    "D": "D — Generative decoys (ours)",
}
APPROACH_MARKER = {"A": "o", "B": "s", "C": "D", "D": "^"}
ENGINE_COLOR = {"mongo": "#2a78d6", "couchbase": "#eb6834", "cassandra": "#1baf7a"}
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

FIG_DIR = os.path.join(config.RESULTS_DIR, "figures")
TABLE_DIR = os.path.join(config.RESULTS_DIR, "tables")


def _style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def load_results() -> pd.DataFrame:
    if not os.path.exists(metrics.RESULTS_CSV):
        raise FileNotFoundError(
            f"{metrics.RESULTS_CSV} not found — run `python -m src.experiments.run_experiment` first."
        )
    df = pd.read_csv(metrics.RESULTS_CSV)
    # raw_results.csv keeps every engine ever run (Couchbase/Cassandra/ArangoDB rows are
    # intentionally left in place, not deleted) but the report is scoped to
    # config.DEFAULT_ENGINES -- currently ["mongo"] -- so tables/figures only reflect the
    # engine(s) actively being reported on. Change DEFAULT_ENGINES to bring others back.
    return df[df["engine"].isin(config.DEFAULT_ENGINES)]


def _value_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows carrying a value-recovery result (excludes the synthetic linkage rows)."""
    return df[df["recovery_accuracy"].notna()]


def _canonical_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """C/D rows are logged once per swept decoy_target_ratio (see run_experiment.py
    --decoy-ratios); Table 1/2/derived_values/Fig 1-3 need exactly one row per
    (engine, approach, scale) or the groupby averages across ratios, which would blur the
    headline number into something no single configuration produced. Pin to
    config.DECOY_TARGET_RATIO (A/B rows have no ratio and pass through unaffected) -- the
    full sweep is reported separately in table_ratio_sweep.md / Fig. 6."""
    has_ratio = df["decoy_target_ratio"].notna()
    return df[~has_ratio | (df["decoy_target_ratio"] == config.DECOY_TARGET_RATIO)]


def _single(df: pd.DataFrame) -> pd.DataFrame:
    return _value_rows(_canonical_ratio(df[df["schema"] == "single"]))


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    sub = _single(df)
    agg = (
        sub.groupby(["engine", "approach", "scale"])
        .agg(
            dataset_source=("dataset_source", "first"),
            mean_latency_ms=("mean_latency_ms", "mean"),
            p95_latency_ms=("p95_latency_ms", "mean"),
            throughput_qps=("throughput_qps", "mean"),
            cpu_percent=("cpu_percent", "mean"),
            storage_mb=("storage_mb", "mean"),
            ciphertext_expansion_factor=("ciphertext_expansion_factor", "mean"),
            recovery_accuracy=("recovery_accuracy", "mean"),
            recovery_accuracy_filtered=("recovery_accuracy_filtered", "mean"),
            n_repeats=("repeat", "count"),
        )
        .reset_index()
        .sort_values(["engine", "scale", "approach"])
    )
    return agg


def write_tables(summary: pd.DataFrame) -> None:
    os.makedirs(TABLE_DIR, exist_ok=True)
    summary.to_csv(os.path.join(TABLE_DIR, "summary.csv"), index=False)

    lines = ["# Benchmark summary (mean across repeats, every scale point, single-collection schema)\n"]
    for engine in sorted(summary["engine"].unique()):
        lines.append(f"\n## {engine}\n")
        sub = summary[summary["engine"] == engine]
        cols = [
            "scale", "approach", "mean_latency_ms", "p95_latency_ms", "throughput_qps",
            "cpu_percent", "storage_mb", "ciphertext_expansion_factor", "recovery_accuracy",
            "recovery_accuracy_filtered",
        ]
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        lines.append(header)
        lines.append(sep)
        for _, row in sub.iterrows():
            filt = f"{row['recovery_accuracy_filtered']:.1%}" if pd.notna(row["recovery_accuracy_filtered"]) else "-"
            vals = [
                str(int(row["scale"])), row["approach"],
                f"{row['mean_latency_ms']:.3f}", f"{row['p95_latency_ms']:.3f}",
                f"{row['throughput_qps']:.1f}", f"{row['cpu_percent']:.1f}",
                f"{row['storage_mb']:.2f}", f"{row['ciphertext_expansion_factor']:.2f}",
                f"{row['recovery_accuracy']:.1%}", filt,
            ]
            lines.append("| " + " | ".join(vals) + " |")
    with open(os.path.join(TABLE_DIR, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_table1_performance(summary: pd.DataFrame) -> pd.DataFrame:
    """Table 1 (B.8): performance per approach x engine at the largest scale point."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale].sort_values(["engine", "approach"])

    lines = [f"# Table 1 — Performance per approach x engine (scale = {scale:,} records)\n"]
    cols = ["engine", "approach", "mean_latency_ms", "p95_latency_ms", "throughput_qps", "cpu_percent", "storage_mb"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, row in sub.iterrows():
        lines.append(
            f"| {row['engine']} | {row['approach']} | {row['mean_latency_ms']:.3f} | "
            f"{row['p95_latency_ms']:.3f} | {row['throughput_qps']:.1f} | {row['cpu_percent']:.1f} | "
            f"{row['storage_mb']:.2f} |"
        )
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table1_performance.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return sub


def write_table2_recovery(summary: pd.DataFrame) -> pd.DataFrame:
    """Table 2 (B.8): value-recovery accuracy per approach x engine, one row per engine."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    pivot = sub.pivot_table(index="engine", columns="approach", values="recovery_accuracy")
    pivot = pivot.reindex(columns=APPROACHES)

    lines = [f"# Table 2 — Value-recovery accuracy per approach x engine (scale = {scale:,} records)\n"]
    lines.append("| engine | A | B | C | D |")
    lines.append("|---|---|---|---|---|")
    for engine, row in pivot.iterrows():
        vals = [f"{row[a]:.1%}" if pd.notna(row[a]) else "-" for a in APPROACHES]
        lines.append(f"| {engine} | " + " | ".join(vals) + " |")
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table2_recovery.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return pivot


def write_table3_linkage(df: pd.DataFrame) -> pd.DataFrame:
    """Table 3 (B.8): cross-collection linkage-recovery accuracy, before (B) vs after (D)."""
    linkage = df[(df["schema"] == "multi") & (df["collection"] == "linkage")]
    if linkage.empty:
        lines = ["# Table 3 — Cross-collection linkage-recovery accuracy\n", "_No multi-schema runs found._\n"]
        os.makedirs(TABLE_DIR, exist_ok=True)
        with open(os.path.join(TABLE_DIR, "table3_linkage.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return pd.DataFrame()

    scale = linkage["scale"].max()
    sub = linkage[linkage["scale"] == scale]
    pivot = sub.pivot_table(index="engine", columns="approach", values="linkage_recovery_accuracy")
    pivot = pivot.reindex(columns=APPROACHES)

    lines = [f"# Table 3 — Cross-collection linkage-recovery accuracy, before (B) vs after (D) (scale = {scale:,})\n"]
    lines.append("| engine | A | B | C | D | B->D drop (pp) |")
    lines.append("|---|---|---|---|---|---|")
    for engine, row in pivot.iterrows():
        b, d = row.get("B"), row.get("D")
        drop = f"{(b - d) * 100:.1f}" if pd.notna(b) and pd.notna(d) else "-"
        vals = [f"{row[a]:.1%}" if pd.notna(row[a]) else "-" for a in APPROACHES]
        lines.append(f"| {engine} | " + " | ".join(vals) + f" | {drop} |")
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table3_linkage.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return pivot


def write_table2b_percollection_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    """Supplementary, NOT part of the headline Table 2 (see module docstring / plan
    B.5.1): patients/billing's own QUERY_FIELD (race_category, cost_category) are lower-
    cardinality / less-skewed than the vetted specific_diagnostic_test, so their
    value-recovery numbers are reported here for transparency, not folded into Table 2."""
    multi = _value_rows(_canonical_ratio(df[(df["schema"] == "multi") & (df["collection"] != "lab_orders")]))
    lines = ["# Table 2b — Supplementary per-collection value-recovery diagnostics (multi-schema)\n"]
    lines.append(
        "_Not a headline result -- `patients`/`race_category` and `billing`/`cost_category` are lower-cardinality "
        "and/or less-skewed than `specific_diagnostic_test`, the only field the plan's B.5.1 sanity check "
        "vetted as an attack target. Reported here for transparency about how the two secondary collections "
        "behave, not as evidence for or against the solution._\n"
    )
    if multi.empty:
        lines.append("_No multi-schema runs found._\n")
    else:
        scale = multi["scale"].max()
        sub = multi[multi["scale"] == scale]
        agg = (
            sub.groupby(["engine", "collection", "approach"])
            .agg(recovery_accuracy=("recovery_accuracy", "mean"), recovery_accuracy_filtered=("recovery_accuracy_filtered", "mean"))
            .reset_index()
            .sort_values(["collection", "engine", "approach"])
        )
        lines.append("| engine | collection | approach | recovery | filtered |")
        lines.append("|---|---|---|---|---|")
        for _, row in agg.iterrows():
            filt = f"{row['recovery_accuracy_filtered']:.1%}" if pd.notna(row["recovery_accuracy_filtered"]) else "-"
            lines.append(f"| {row['engine']} | {row['collection']} | {row['approach']} | {row['recovery_accuracy']:.1%} | {filt} |")
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table2b_percollection_diagnostics.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return multi


def write_ratio_sweep(df: pd.DataFrame) -> pd.DataFrame:
    """decoy_target_ratio as an independent variable (plan B.2), not a tuned constant:
    more flattening lowers recovery but raises storage -- report the curve, not one point.
    Scoped to lab_orders/specific_diagnostic_test, the vetted field, single-schema."""
    sub = df[(df["schema"] == "single") & (df["approach"].isin(["C", "D"])) & df["decoy_target_ratio"].notna()]
    if sub.empty:
        lines = ["# decoy_target_ratio sweep\n", "_No sweep runs found (need >1 value in --decoy-ratios)._\n"]
        os.makedirs(TABLE_DIR, exist_ok=True)
        with open(os.path.join(TABLE_DIR, "table_ratio_sweep.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return pd.DataFrame()

    scale = sub["scale"].max()
    sub = sub[sub["scale"] == scale]
    agg = (
        sub.groupby(["engine", "approach", "decoy_target_ratio"])
        .agg(
            recovery_accuracy_filtered=("recovery_accuracy_filtered", "mean"),
            storage_mb=("storage_mb", "mean"),
            ciphertext_expansion_factor=("ciphertext_expansion_factor", "mean"),
        )
        .reset_index()
        .sort_values(["engine", "approach", "decoy_target_ratio"])
    )
    lines = [f"# decoy_target_ratio sweep -- security vs. storage trade-off (lab_orders, scale = {scale:,})\n"]
    lines.append("| engine | approach | ratio | recovery (filtered) | storage_mb | expansion |")
    lines.append("|---|---|---|---|---|---|")
    for _, row in agg.iterrows():
        lines.append(
            f"| {row['engine']} | {row['approach']} | {row['decoy_target_ratio']} | "
            f"{row['recovery_accuracy_filtered']:.1%} | {row['storage_mb']:.2f} | {row['ciphertext_expansion_factor']:.2f}x |"
        )
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table_ratio_sweep.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return agg


def plot_fig6_ratio_sweep(ratio_agg: pd.DataFrame) -> None:
    if ratio_agg.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for approach in ("C", "D"):
        for engine in sorted(ratio_agg["engine"].unique()):
            s = ratio_agg[(ratio_agg["approach"] == approach) & (ratio_agg["engine"] == engine)].sort_values("decoy_target_ratio")
            if s.empty:
                continue
            style = "-" if engine == sorted(ratio_agg["engine"].unique())[0] else "--"
            axes[0].plot(s["decoy_target_ratio"], s["recovery_accuracy_filtered"], style, marker="o",
                         color=APPROACH_COLOR[approach], label=f"{APPROACH_LABEL[approach]} ({engine})")
            axes[1].plot(s["decoy_target_ratio"], s["ciphertext_expansion_factor"], style, marker="o",
                         color=APPROACH_COLOR[approach], label=f"{APPROACH_LABEL[approach]} ({engine})")
    axes[0].set_xlabel("decoy_target_ratio", color=MUTED)
    axes[0].set_ylabel("Recovery accuracy (filtered)", color=MUTED)
    axes[0].set_title("(a) Security: more flattening -> lower recovery", color=INK, fontsize=11, fontweight="bold")
    axes[1].set_xlabel("decoy_target_ratio", color=MUTED)
    axes[1].set_ylabel("Storage-expansion factor (x)", color=MUTED)
    axes[1].set_title("(b) Cost: more flattening -> more storage", color=INK, fontsize=11, fontweight="bold")
    for ax in axes:
        _style_axes(ax)
    axes[0].legend(frameon=False, fontsize=7, loc="upper right")
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle("Fig. 6 — decoy_target_ratio as an independent variable: security vs. storage (lab_orders)",
                 color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig6_ratio_sweep.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def compute_derived_values(raw_df: pd.DataFrame, summary: pd.DataFrame) -> None:
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    lines = [f"# Derived values (scale = {scale:,} records unless noted)\n"]

    lines.append("\n## Latency overhead vs. Approach A, per engine\n")
    lines.append("| engine | approach | mean_latency_ms | overhead vs A |")
    lines.append("|---|---|---|---|")
    for engine in sorted(sub["engine"].unique()):
        a_lat = sub[(sub["engine"] == engine) & (sub["approach"] == "A")]["mean_latency_ms"]
        if a_lat.empty:
            continue
        a_lat = a_lat.iloc[0]
        for approach in APPROACHES:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            if row.empty:
                continue
            lat = row["mean_latency_ms"].iloc[0]
            overhead = (lat - a_lat) / a_lat * 100 if a_lat else 0.0
            lines.append(f"| {engine} | {approach} | {lat:.3f} | {overhead:+.1f}% |")

    lines.append("\n## Storage-expansion factor vs. Approach A, per engine\n")
    lines.append("| engine | approach | expansion factor |")
    lines.append("|---|---|---|")
    for _, row in sub.sort_values(["engine", "approach"]).iterrows():
        lines.append(f"| {row['engine']} | {row['approach']} | {row['ciphertext_expansion_factor']:.2f}x |")

    lines.append("\n## B -> D and C -> D recovery-accuracy drop (headline security result)\n")
    lines.append("| engine | B accuracy | C accuracy (filtered) | D accuracy (filtered) | B->D drop (pp) | C->D drop under filter (pp) |")
    lines.append("|---|---|---|---|---|---|")
    for engine in sorted(sub["engine"].unique()):
        b_row = sub[(sub["engine"] == engine) & (sub["approach"] == "B")]
        c_row = sub[(sub["engine"] == engine) & (sub["approach"] == "C")]
        d_row = sub[(sub["engine"] == engine) & (sub["approach"] == "D")]
        if b_row.empty or c_row.empty or d_row.empty:
            continue
        b_acc = b_row["recovery_accuracy"].iloc[0]
        c_acc_f = c_row["recovery_accuracy_filtered"].iloc[0]
        d_acc_f = d_row["recovery_accuracy_filtered"].iloc[0]
        lines.append(
            f"| {engine} | {b_acc:.1%} | {c_acc_f:.1%} | {d_acc_f:.1%} | "
            f"{(b_acc - d_acc_f) * 100:.1f} | {(c_acc_f - d_acc_f) * 100:.1f} |"
        )

    lines.append("\n## Run-to-run variance across repeats (scale = largest, single schema)\n")
    lines.append("| engine | approach | latency std (ms) | latency 95% CI (+-ms) | accuracy std | n repeats |")
    lines.append("|---|---|---|---|---|---|")
    raw_at_scale = _single(raw_df[raw_df["scale"] == scale])
    for (engine, approach), g in raw_at_scale.groupby(["engine", "approach"]):
        n = len(g)
        lat_std = g["mean_latency_ms"].std(ddof=1) if n > 1 else 0.0
        lat_ci = 1.96 * lat_std / np.sqrt(n) if n > 1 else 0.0
        acc_std = g["recovery_accuracy"].std(ddof=1) if n > 1 else 0.0
        lines.append(f"| {engine} | {approach} | {lat_std:.3f} | {lat_ci:.3f} | {acc_std:.3f} | {n} |")

    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "derived_values.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot_fig1_latency_vs_scale(summary: pd.DataFrame) -> None:
    engines = sorted(summary["engine"].unique())
    fig, axes = plt.subplots(1, len(engines), figsize=(6 * len(engines), 4.5), sharey=True)
    if len(engines) == 1:
        axes = [axes]
    for ax, engine in zip(axes, engines):
        sub = summary[summary["engine"] == engine]
        for approach in APPROACHES:
            s = sub[sub["approach"] == approach].sort_values("scale")
            if s.empty:
                continue
            ax.plot(
                s["scale"], s["mean_latency_ms"], marker="o", markersize=6, linewidth=2,
                color=APPROACH_COLOR[approach], label=APPROACH_LABEL[approach],
            )
        ax.set_xscale("log")
        ax.set_xlabel("Dataset scale (records)", color=MUTED)
        ax.set_title(engine, color=INK, fontsize=12, fontweight="bold")
        _style_axes(ax)
    axes[0].set_ylabel("Mean query latency (ms)", color=MUTED)
    axes[-1].legend(frameon=False, loc="upper left", fontsize=8)
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle("Fig. 1 — Query latency vs. dataset scale, by approach", color=INK, fontsize=13, fontweight="bold")
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig1_latency_vs_scale.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_fig2_recovery_accuracy(summary: pd.DataFrame) -> None:
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    engines = sorted(sub["engine"].unique())

    fig, ax = plt.subplots(figsize=(9, 5.5))
    width = 0.8 / max(len(engines), 1)
    x = np.arange(len(APPROACHES))
    for i, engine in enumerate(engines):
        vals = []
        for approach in APPROACHES:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            if row.empty:
                vals.append(0)
            elif approach in ("C", "D") and pd.notna(row["recovery_accuracy_filtered"].iloc[0]):
                vals.append(row["recovery_accuracy_filtered"].iloc[0])
            else:
                vals.append(row["recovery_accuracy"].iloc[0])
        offset = (i - (len(engines) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width=width, color=ENGINE_COLOR.get(engine, "#4a3aa7"), label=engine)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.0%}", ha="center", va="bottom",
                    fontsize=8, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels([APPROACH_LABEL[a] for a in APPROACHES], color=INK, fontsize=8)
    ax.set_ylabel("Attacker query-recovery accuracy\n(C/D shown after the realism filter)", color=MUTED)
    ax.set_title(
        f"Fig. 2 — Leakage-abuse recovery accuracy by approach and engine\n(scale = {scale:,} records)",
        color=INK, fontsize=12, fontweight="bold",
    )
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=len(engines))
    ax.set_ylim(top=1.15)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig2_recovery_accuracy.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_fig3_tradeoff(summary: pd.DataFrame) -> None:
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for engine in sorted(sub["engine"].unique()):
        a_row = sub[(sub["engine"] == engine) & (sub["approach"] == "A")]
        if a_row.empty:
            continue
        a_lat = a_row["mean_latency_ms"].iloc[0]
        for approach in APPROACHES:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            if row.empty:
                continue
            lat = row["mean_latency_ms"].iloc[0]
            overhead = (lat - a_lat) / a_lat * 100 if a_lat else 0.0
            acc = row["recovery_accuracy"].iloc[0]
            ax.scatter(
                overhead, acc, s=140, color=ENGINE_COLOR.get(engine, "#4a3aa7"),
                marker=APPROACH_MARKER[approach], edgecolors=SURFACE, linewidths=1.5, zorder=3,
            )
            ax.annotate(
                f"{engine[:2].upper()}-{approach}", (overhead, acc), textcoords="offset points",
                xytext=(6, 6), fontsize=8, color=MUTED,
            )

    from matplotlib.lines import Line2D
    engine_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markersize=9, label=e)
        for e, c in ENGINE_COLOR.items() if e in sub["engine"].unique()
    ]
    approach_handles = [
        Line2D([0], [0], marker=APPROACH_MARKER[a], color="none", markerfacecolor=MUTED, markersize=9,
               label=APPROACH_LABEL[a])
        for a in APPROACHES
    ]
    leg1 = ax.legend(handles=engine_handles, title="Engine (color)", frameon=False, loc="upper left", fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=approach_handles, title="Approach (marker)", frameon=False, loc="lower right", fontsize=8)

    ax.set_xlabel("Latency overhead vs. Approach A (%)", color=MUTED)
    ax.set_ylabel("Attacker query-recovery accuracy (unfiltered)", color=MUTED)
    ax.set_title(f"Fig. 3 — Security-performance trade-off\n(scale = {scale:,} records)", color=INK, fontsize=12, fontweight="bold")
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig3_tradeoff_scatter.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_storage_expansion(summary: pd.DataFrame) -> None:
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    engines = sorted(sub["engine"].unique())

    fig, ax = plt.subplots(figsize=(8, 5))
    width = 0.8 / max(len(APPROACHES), 1)
    x = np.arange(len(engines))
    for i, approach in enumerate(APPROACHES):
        vals = []
        for engine in engines:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            vals.append(row["ciphertext_expansion_factor"].iloc[0] if not row.empty else 0)
        bars = ax.bar(x + (i - 1.5) * width, vals, width=width, color=APPROACH_COLOR[approach], label=APPROACH_LABEL[approach])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.2f}", ha="center", va="bottom",
                    fontsize=7, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels(engines, color=INK)
    ax.set_ylabel("Storage size vs. plaintext baseline (x)", color=MUTED)
    ax.set_title(f"Storage-expansion factor by approach and engine\n(scale = {scale:,} records)", color=INK, fontsize=12, fontweight="bold")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=4, fontsize=8)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.15)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "storage_expansion.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


LEAK = "#c1352b"
SAFE = "#1baf7a"


def plot_fig4_data_view() -> None:
    """Fig. 4 (B.8): the same lab_orders record shown as plaintext (A), encrypted (B),
    and encrypted-with-solution (D), row-aligned across panels with the leaked/protected
    fields colour- and badge-coded so the *change* is legible at a glance, not just the
    raw hex. The patient_code row additionally shows the *same* patient's token in
    `billing` alongside it, so B's identical-token linkage and D's divergent-token
    protection are both visible directly in this figure, not only in Fig. 5."""
    df, _ = dataset.load_scaled_dataset(min(1_000, dataset.full_dataset_size()))
    lab_orders = schema.build_lab_orders(df)
    sample_row = lab_orders.iloc[0]
    value = str(sample_row[config.SENSITIVE_FIELD])
    patient_code = str(sample_row[config.LINK_FIELD])

    b_key = encryption.derive_token_key(None)
    d_key_lab = encryption.derive_token_key("lab_orders")
    d_key_bill = encryption.derive_token_key("billing")

    def short(tok: bytes) -> str:
        return tok.hex()[:20] + "..."

    b_val_tok = short(encryption.deterministic_token(value, key=b_key))
    b_pat_tok_lab = short(encryption.deterministic_token(patient_code, key=b_key))
    b_pat_tok_bill = short(encryption.deterministic_token(patient_code, key=b_key))  # same key -> identical
    d_val_tok = short(encryption.deterministic_token(value, key=d_key_lab))
    d_pat_tok_lab = short(encryption.deterministic_token(patient_code, key=d_key_lab))
    d_pat_tok_bill = short(encryption.deterministic_token(patient_code, key=d_key_bill))  # different key -> diverges

    # (row label, A value, B value, B badge, D value, D badge)
    rows = [
        ("record_id", str(sample_row["record_id"]), str(sample_row["record_id"]), None, "<secret id(i), opaque>", None),
        (config.SENSITIVE_FIELD, value, b_val_tok, ("SAME VALUE -> SAME TOKEN", LEAK), d_val_tok, ("HIDDEN AMONG DECOYS", SAFE)),
        ("patient_code (in lab_orders)", patient_code, b_pat_tok_lab, None, d_pat_tok_lab, None),
        ("patient_code (in billing)", patient_code, b_pat_tok_bill, ("IDENTICAL -> LINKABLE", LEAK), d_pat_tok_bill, ("DIFFERENT -> NOT LINKABLE", SAFE)),
    ]

    n = len(rows)
    row_h = 1.0  # each row's vertical slot, including its own gap
    box_h = 0.8  # the box drawn inside that slot (leaves a visible gap between rows)
    header_h = 1.0
    top = n * row_h + header_h

    fig, ax = plt.subplots(figsize=(15, 2.0 + 1.15 * n))
    ax.set_xlim(-0.62, 3)
    ax.set_ylim(-0.9, top + 0.15)
    ax.axis("off")
    fig.patch.set_facecolor(SURFACE)

    col_titles = ["A — Plaintext (readable by the server)", "B — Deterministic (leaks)", "D — Generative decoys (ours)"]
    col_colors = [MUTED, LEAK, SAFE]
    header_bottom = n * row_h
    for c, (title, color) in enumerate(zip(col_titles, col_colors)):
        ax.add_patch(plt.Rectangle((c, header_bottom), 1, header_h, facecolor=color, alpha=0.12, edgecolor="none"))
        ax.text(c + 0.5, header_bottom + header_h / 2, title, ha="center", va="center", fontsize=10.5,
                fontweight="bold", color=color, wrap=True)

    for r, (label, a_val, b_val, b_badge, d_val, d_badge) in enumerate(rows):
        row_top = (n - r) * row_h  # top of this row's slot (header sits just above row 0's slot)
        box_bottom = row_top - box_h
        ax.text(-0.05, box_bottom + box_h / 2, label, ha="right", va="center", fontsize=8.5, color=MUTED,
                fontweight="bold", wrap=True)
        for c, (val, badge) in enumerate([(a_val, None), (b_val, b_badge), (d_val, d_badge)]):
            ax.add_patch(plt.Rectangle((c + 0.03, box_bottom), 0.94, box_h, facecolor="white", edgecolor=GRID, linewidth=1))
            text_y = box_bottom + (box_h * 0.68 if badge else box_h * 0.5)
            ax.text(c + 0.08, text_y, val, ha="left", va="center", fontsize=8.5, family="monospace", color=INK)
            if badge:
                text, color = badge
                ax.text(c + 0.08, box_bottom + box_h * 0.25, text, ha="left", va="center", fontsize=7.5,
                        fontweight="bold", color=color)

    ax.text(-0.05, -0.55, "Same underlying record throughout -- compare each row left-to-right. Red badges = what an "
            "observing server can exploit; green badges = what the solution changes.",
            ha="left", va="top", fontsize=8.5, color=MUTED, style="italic")

    fig.suptitle("Fig. 4 — Before/after data view (one example lab_orders + billing record pair)", color=INK, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig4_data_view.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_fig5_metadata_view() -> None:
    """Fig. 5 (B.8): (a) frequency histogram before/after decoys, (b) linkage diagram
    (same patient_code -> shared token before, divergent tokens after), (c) name
    tokenisation example."""
    df, _ = dataset.load_scaled_dataset(min(10_000, dataset.full_dataset_size()))
    lab_orders = schema.build_lab_orders(df)
    value_counts = lab_orders[config.SENSITIVE_FIELD].astype(str).value_counts()
    target_counts = decoys.compute_target_counts(value_counts.to_dict())
    after_counts = pd.Series({v: value_counts[v] + target_counts.get(v, 0) for v in value_counts.index})

    top_n = 15
    top_values = value_counts.head(top_n).index

    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 2)

    ax_hist = fig.add_subplot(gs[0, :])
    x = np.arange(len(top_values))
    width = 0.38
    ax_hist.bar(x - width / 2, value_counts[top_values], width=width, color=APPROACH_COLOR["B"], label="B — before (raw frequency)")
    ax_hist.bar(x + width / 2, after_counts[top_values], width=width, color=APPROACH_COLOR["D"], label="D — after decoys (flattened)")
    ax_hist.set_xticks(x)
    ax_hist.set_xticklabels(top_values, rotation=60, ha="right", fontsize=7, color=INK)
    ax_hist.set_ylabel("Observed record count", color=MUTED)
    ax_hist.set_title("(a) Sensitive-field frequency, top 15 values: before vs. after decoys", color=INK, fontsize=11, fontweight="bold")
    ax_hist.legend(frameon=False)
    _style_axes(ax_hist)

    ax_link = fig.add_subplot(gs[1, 0])
    ax_link.axis("off")
    ax_link.set_title("(b) Cross-collection linkage token", color=INK, fontsize=11, fontweight="bold")
    sample_code = str(lab_orders.iloc[0][config.LINK_FIELD])
    b_key = encryption.derive_token_key(None)
    tok_patients_b = encryption.deterministic_token(sample_code, key=b_key).hex()[:12]
    tok_billing_b = tok_patients_b
    tok_patients_d = encryption.deterministic_token(sample_code, key=encryption.derive_token_key("patients")).hex()[:12]
    tok_billing_d = encryption.deterministic_token(sample_code, key=encryption.derive_token_key("billing")).hex()[:12]
    ax_link.text(0.0, 0.85, f"patient_code = {sample_code}", fontsize=9, family="monospace", color=INK)
    ax_link.text(0.0, 0.65, f"Before (B/C, shared key):\n  patients token  = {tok_patients_b}...\n  billing  token  = {tok_billing_b}...  (equal -> linkable)",
                 fontsize=8.5, family="monospace", color="#eb6834")
    ax_link.text(0.0, 0.25, f"After (D, per-collection keys):\n  patients token  = {tok_patients_d}...\n  billing  token  = {tok_billing_d}...  (different -> not linkable)",
                 fontsize=8.5, family="monospace", color="#1baf7a")

    ax_name = fig.add_subplot(gs[1, 1])
    ax_name.axis("off")
    ax_name.set_title("(c) Collection/field name tokenisation", color=INK, fontsize=11, fontweight="bold")
    rows = [("patients", encryption.tokenize_name("patients")), ("lab_orders", encryption.tokenize_name("lab_orders")),
            ("billing", encryption.tokenize_name("billing")), (config.SENSITIVE_FIELD, encryption.tokenize_name(config.SENSITIVE_FIELD))]
    y = 0.85
    for plain, tok in rows:
        ax_name.text(0.0, y, f"{plain}  ->  {tok}", fontsize=9, family="monospace", color=INK)
        y -= 0.2

    fig.patch.set_facecolor(SURFACE)
    fig.suptitle("Fig. 5 — Before/after metadata view", color=INK, fontsize=13, fontweight="bold")
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig5_metadata_view.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    df = load_results()
    summary = summarize(df)
    write_tables(summary)
    write_table1_performance(summary)
    write_table2_recovery(summary)
    write_table2b_percollection_diagnostics(df)
    write_table3_linkage(df)
    ratio_agg = write_ratio_sweep(df)
    compute_derived_values(df, summary)
    plot_fig1_latency_vs_scale(summary)
    plot_fig2_recovery_accuracy(summary)
    plot_fig3_tradeoff(summary)
    plot_storage_expansion(summary)
    plot_fig4_data_view()
    plot_fig5_metadata_view()
    plot_fig6_ratio_sweep(ratio_agg)
    print(f"Wrote tables to {TABLE_DIR}/ and figures to {FIG_DIR}/")


if __name__ == "__main__":
    main()
