"""Builds the Results-section tables and figures from results/raw_results.csv.

Usage:
    python -m src.analysis.generate_report

Produces the five named deliverables from plan B.8 plus the derived values the
Discussion section is written around:
    results/tables/table1_performance.md   Table 1 — performance per approach x engine (largest scale)
    results/tables/table2_recovery.md      Table 2 — recovery accuracy per approach x engine
    results/tables/derived_values.md       overhead %, expansion factor, B->C drop, cross-engine range, ...
    results/tables/summary.md/.csv         full per-scale summary (all scales, all metrics)
    results/figures/fig1_latency_vs_scale.png
    results/figures/fig2_recovery_accuracy.png
    results/figures/fig3_tradeoff_scatter.png
    results/figures/storage_expansion.png  (bonus, not a named B.8 deliverable)
"""
from __future__ import annotations

import os

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

from src.core import config, metrics

APPROACH_COLOR = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
APPROACH_LABEL = {"A": "A — Plaintext", "B": "B — Deterministic (leaks)", "C": "C — Leakage-reduced"}
APPROACH_MARKER = {"A": "o", "B": "s", "C": "^"}
ENGINE_COLOR = {"postgres": "#2a78d6", "mongo": "#eb6834"}
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
    return pd.read_csv(metrics.RESULTS_CSV)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    agg = (
        df.groupby(["engine", "approach", "scale"])
        .agg(
            dataset_source=("dataset_source", "first"),
            mean_latency_ms=("mean_latency_ms", "mean"),
            p95_latency_ms=("p95_latency_ms", "mean"),
            throughput_qps=("throughput_qps", "mean"),
            cpu_percent=("cpu_percent", "mean"),
            storage_mb=("storage_mb", "mean"),
            ciphertext_expansion_factor=("ciphertext_expansion_factor", "mean"),
            recovery_accuracy=("recovery_accuracy", "mean"),
            n_repeats=("repeat", "count"),
        )
        .reset_index()
        .sort_values(["engine", "scale", "approach"])
    )
    return agg


def write_tables(summary: pd.DataFrame) -> None:
    os.makedirs(TABLE_DIR, exist_ok=True)
    summary.to_csv(os.path.join(TABLE_DIR, "summary.csv"), index=False)

    lines = ["# Benchmark summary (mean across repeats, every scale point)\n"]
    for engine in sorted(summary["engine"].unique()):
        lines.append(f"\n## {engine}\n")
        sub = summary[summary["engine"] == engine]
        cols = [
            "scale", "approach", "mean_latency_ms", "p95_latency_ms", "throughput_qps",
            "cpu_percent", "storage_mb", "ciphertext_expansion_factor", "recovery_accuracy",
        ]
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        lines.append(header)
        lines.append(sep)
        for _, row in sub.iterrows():
            vals = [
                str(int(row["scale"])), row["approach"],
                f"{row['mean_latency_ms']:.3f}", f"{row['p95_latency_ms']:.3f}",
                f"{row['throughput_qps']:.1f}", f"{row['cpu_percent']:.1f}",
                f"{row['storage_mb']:.2f}", f"{row['ciphertext_expansion_factor']:.2f}",
                f"{row['recovery_accuracy']:.1%}",
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
    """Table 2 (B.8): recovery accuracy per approach x engine, one row per engine."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    pivot = sub.pivot_table(index="engine", columns="approach", values="recovery_accuracy")
    pivot = pivot.reindex(columns=["A", "B", "C"])

    lines = [f"# Table 2 — Recovery accuracy per approach x engine (scale = {scale:,} records)\n"]
    lines.append("| engine | A | B | C |")
    lines.append("|---|---|---|---|")
    for engine, row in pivot.iterrows():
        lines.append(f"| {engine} | {row['A']:.1%} | {row['B']:.1%} | {row['C']:.1%} |")
    os.makedirs(TABLE_DIR, exist_ok=True)
    with open(os.path.join(TABLE_DIR, "table2_recovery.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return pivot


def compute_derived_values(raw_df: pd.DataFrame, summary: pd.DataFrame) -> None:
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    lines = [f"# Derived values (scale = {scale:,} records unless noted)\n"]

    # Performance overhead of B and C relative to A, per engine (latency-based).
    lines.append("\n## Latency overhead vs. Approach A, per engine\n")
    lines.append("| engine | approach | mean_latency_ms | overhead vs A |")
    lines.append("|---|---|---|---|")
    for engine in sorted(sub["engine"].unique()):
        a_lat = sub[(sub["engine"] == engine) & (sub["approach"] == "A")]["mean_latency_ms"]
        if a_lat.empty:
            continue
        a_lat = a_lat.iloc[0]
        for approach in ["A", "B", "C"]:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            if row.empty:
                continue
            lat = row["mean_latency_ms"].iloc[0]
            overhead = (lat - a_lat) / a_lat * 100 if a_lat else 0.0
            lines.append(f"| {engine} | {approach} | {lat:.3f} | {overhead:+.1f}% |")

    # Storage-expansion factor of B and C vs A.
    lines.append("\n## Storage-expansion factor vs. Approach A, per engine\n")
    lines.append("| engine | approach | expansion factor |")
    lines.append("|---|---|---|")
    for _, row in sub.sort_values(["engine", "approach"]).iterrows():
        lines.append(f"| {row['engine']} | {row['approach']} | {row['ciphertext_expansion_factor']:.2f}x |")

    # B -> C recovery-accuracy drop, per engine (headline security result).
    lines.append("\n## B -> C recovery-accuracy drop (headline security result)\n")
    lines.append("| engine | B accuracy | C accuracy | drop (pp) |")
    lines.append("|---|---|---|---|")
    b_accs = {}
    for engine in sorted(sub["engine"].unique()):
        b_row = sub[(sub["engine"] == engine) & (sub["approach"] == "B")]
        c_row = sub[(sub["engine"] == engine) & (sub["approach"] == "C")]
        if b_row.empty or c_row.empty:
            continue
        b_acc = b_row["recovery_accuracy"].iloc[0]
        c_acc = c_row["recovery_accuracy"].iloc[0]
        b_accs[engine] = b_acc
        lines.append(f"| {engine} | {b_acc:.1%} | {c_acc:.1%} | {(b_acc - c_acc) * 100:.1f} pp |")

    # Range of Approach-B accuracy across engines (cross-engine consistency).
    if b_accs:
        lines.append("\n## Cross-engine consistency of Approach B\n")
        lines.append(
            f"Approach-B recovery accuracy ranges from **{min(b_accs.values()):.1%}** to "
            f"**{max(b_accs.values()):.1%}** across engines "
            f"(spread: {(max(b_accs.values()) - min(b_accs.values())) * 100:.1f} pp) — "
            "the leakage is strategy-intrinsic, not engine-specific, if this spread is small."
        )

    # Ranking of engines by Approach-C overhead (lowest = cheapest confidentiality).
    lines.append("\n## Engines ranked by Approach-C latency overhead (lowest first)\n")
    c_overheads = []
    for engine in sorted(sub["engine"].unique()):
        a_row = sub[(sub["engine"] == engine) & (sub["approach"] == "A")]
        c_row = sub[(sub["engine"] == engine) & (sub["approach"] == "C")]
        if a_row.empty or c_row.empty:
            continue
        a_lat = a_row["mean_latency_ms"].iloc[0]
        c_lat = c_row["mean_latency_ms"].iloc[0]
        overhead = (c_lat - a_lat) / a_lat * 100 if a_lat else 0.0
        c_overheads.append((engine, overhead))
    c_overheads.sort(key=lambda t: t[1])
    lines.append("| rank | engine | Approach-C overhead |")
    lines.append("|---|---|---|")
    for i, (engine, overhead) in enumerate(c_overheads, start=1):
        lines.append(f"| {i} | {engine} | {overhead:+.1f}% |")

    # Variance / approx. 95% CI across repeats, at the largest scale.
    lines.append("\n## Run-to-run variance across repeats (scale = largest)\n")
    lines.append("| engine | approach | latency std (ms) | latency 95% CI (+-ms) | accuracy std | n repeats |")
    lines.append("|---|---|---|---|---|---|")
    raw_at_scale = raw_df[raw_df["scale"] == scale]
    for (engine, approach), g in raw_at_scale.groupby(["engine", "approach"]):
        n = len(g)
        lat_std = g["mean_latency_ms"].std(ddof=1) if n > 1 else 0.0
        lat_ci = 1.96 * lat_std / np.sqrt(n) if n > 1 else 0.0
        acc_std = g["recovery_accuracy"].std(ddof=1) if n > 1 else 0.0
        lines.append(f"| {engine} | {approach} | {lat_std:.3f} | {lat_ci:.3f} | {acc_std:.3f} | {n} |")
    if raw_at_scale.groupby(["engine", "approach"]).size().min() < 5:
        lines.append(
            "\n_Note: with < 5 repeats the normal-approximation 95% CI above is indicative only — "
            "report it as such, not as a precise interval._"
        )

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
        for approach in ["A", "B", "C"]:
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
    axes[-1].legend(frameon=False, loc="upper left")
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle("Fig. 1 — Query latency vs. dataset scale, by approach", color=INK, fontsize=13, fontweight="bold")
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig1_latency_vs_scale.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_fig2_recovery_accuracy(summary: pd.DataFrame) -> None:
    """Fig. 2 (B.8): x = approach, bars = engine, y = recovery accuracy %."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    approaches = ["A", "B", "C"]
    engines = sorted(sub["engine"].unique())

    fig, ax = plt.subplots(figsize=(8, 5))
    width = 0.35
    x = np.arange(len(approaches))
    for i, engine in enumerate(engines):
        vals = []
        for approach in approaches:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            vals.append(row["recovery_accuracy"].iloc[0] if not row.empty else 0)
        offset = (i - (len(engines) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width=width, color=ENGINE_COLOR.get(engine, "#4a3aa7"), label=engine)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.0%}", ha="center", va="bottom",
                    fontsize=9, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels([APPROACH_LABEL[a] for a in approaches], color=INK)
    ax.set_ylabel("Attacker query-recovery accuracy", color=MUTED)
    ax.set_title(
        f"Fig. 2 — Leakage-abuse recovery accuracy by approach and engine\n(scale = {scale:,} records)",
        color=INK, fontsize=12, fontweight="bold",
    )
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=len(engines))
    ax.set_ylim(top=1.15)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig2_recovery_accuracy.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_fig3_tradeoff(summary: pd.DataFrame) -> None:
    """Fig. 3 (B.8): x = latency overhead % vs. A baseline, y = recovery accuracy %,
    one point per (approach, engine) at the largest scale."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for engine in sorted(sub["engine"].unique()):
        a_row = sub[(sub["engine"] == engine) & (sub["approach"] == "A")]
        if a_row.empty:
            continue
        a_lat = a_row["mean_latency_ms"].iloc[0]
        for approach in ["A", "B", "C"]:
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

    # Legends: engine by color, approach by marker shape.
    from matplotlib.lines import Line2D
    engine_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markersize=9, label=e)
        for e, c in ENGINE_COLOR.items() if e in sub["engine"].unique()
    ]
    approach_handles = [
        Line2D([0], [0], marker=APPROACH_MARKER[a], color="none", markerfacecolor=MUTED, markersize=9,
               label=APPROACH_LABEL[a])
        for a in ["A", "B", "C"]
    ]
    leg1 = ax.legend(handles=engine_handles, title="Engine (color)", frameon=False, loc="upper left")
    ax.add_artist(leg1)
    ax.legend(handles=approach_handles, title="Approach (marker)", frameon=False, loc="lower right")

    ax.set_xlabel("Latency overhead vs. Approach A (%)", color=MUTED)
    ax.set_ylabel("Attacker query-recovery accuracy", color=MUTED)
    ax.set_title(
        f"Fig. 3 — Security-performance trade-off\n(scale = {scale:,} records)",
        color=INK, fontsize=12, fontweight="bold",
    )
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "fig3_tradeoff_scatter.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_storage_expansion(summary: pd.DataFrame) -> None:
    """Bonus chart (not a named B.8 deliverable): x = engine, bars = approach."""
    scale = summary["scale"].max()
    sub = summary[summary["scale"] == scale]
    engines = sorted(sub["engine"].unique())
    approaches = ["A", "B", "C"]

    fig, ax = plt.subplots(figsize=(8, 5))
    width = 0.25
    x = np.arange(len(engines))
    for i, approach in enumerate(approaches):
        vals = []
        for engine in engines:
            row = sub[(sub["engine"] == engine) & (sub["approach"] == approach)]
            vals.append(row["ciphertext_expansion_factor"].iloc[0] if not row.empty else 0)
        bars = ax.bar(x + (i - 1) * width, vals, width=width, color=APPROACH_COLOR[approach], label=APPROACH_LABEL[approach])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.2f}", ha="center", va="bottom",
                    fontsize=8, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels(engines, color=INK)
    ax.set_ylabel("Storage size vs. plaintext baseline (x)", color=MUTED)
    ax.set_title(f"Ciphertext expansion factor by approach and engine\n(scale = {scale:,} records)",
                 color=INK, fontsize=12, fontweight="bold")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.12)
    _style_axes(ax)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "storage_expansion.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    df = load_results()
    summary = summarize(df)
    write_tables(summary)
    write_table1_performance(summary)
    write_table2_recovery(summary)
    compute_derived_values(df, summary)
    plot_fig1_latency_vs_scale(summary)
    plot_fig2_recovery_accuracy(summary)
    plot_fig3_tradeoff(summary)
    plot_storage_expansion(summary)
    print(f"Wrote tables to {TABLE_DIR}/ and figures to {FIG_DIR}/")


if __name__ == "__main__":
    main()
