"""Two figures built from real, actually-computed output (not illustrations):

1. `concept_scale_comparison.png` -- what the three scale points (1,000 / 10,000 / 30,000)
   actually contain, computed from the real dataset, so a reader knows what each scale means
   rather than treating them as arbitrary numbers.
2. `concept_attack_value_output.png` -- the real value-recovery attack's per-token output
   (observed volume, guessed value, true value, correct/wrong) for Approach B vs. Approach D
   at full flattening, read directly from `attack.token_guess_table` -- the same function
   `run_count_attack`'s accuracy numbers come from, not a re-implementation for display.
3. `concept_attack_linkage_output.png` -- the real linkage attack's per-patient output: the
   same `patient_code` token compared across `patients`/`billing` under B (shared key) vs.
   D (per-collection keys), read directly from `attack.run_linkage_attack`'s inputs.

Usage:
    python -m src.analysis.generate_concept_figures
"""
from __future__ import annotations

import os
import textwrap
from collections import defaultdict

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

from src.core import config, dataset, encryption, records, schema, workload
from src.core.attack import ExecutedQuery, run_linkage_attack, token_guess_table
from src.analysis.generate_report import FIG_DIR, GRID, INK, MUTED, SURFACE
from src.analysis.generate_approach_examples import _short, _short_id, _table

LEAK = "#c1352b"
SAFE = "#1baf7a"


# ---------------------------------------------------------------------------
# 1. Scale comparison
# ---------------------------------------------------------------------------

def plot_scale_comparison() -> None:
    full = dataset.full_dataset_size()
    rows = []
    for scale in [1_000, 10_000, 30_000]:
        df, _ = dataset.load_scaled_dataset(scale)
        vc = df[config.SENSITIVE_FIELD].value_counts()
        rows.append(
            [
                f"{scale:,}",
                f"{scale / full * 100:.2f}%",
                str(vc.shape[0]),
                str(vc.iloc[0]),
                vc.index[0],
            ]
        )

    fig, ax = plt.subplots(figsize=(12.5, 3.6))
    fig.patch.set_facecolor(SURFACE)
    _table(
        ax,
        ["scale (records)", "% of full dataset", "distinct test names seen", "count of the most common test", "most common test"],
        rows, col_widths=[0.16, 0.16, 0.2, 0.22, 0.26],
    )
    ax.text(
        0.0, -0.1,
        f"All three are the same kind of sample -- a seeded, no-replacement random draw from the same real "
        f"{full:,}-record dataset, so results at different scales are directly comparable, not different datasets. "
        "Why three points, not one: 1,000 is small enough to iterate on quickly and catch mistakes early, but "
        "has thin repeat-counts per value; 30,000 is where storage/latency overhead and the security cliff (Fig. 2) "
        "become clearly visible; 10,000 sits in between and confirms the pattern holds as data grows, not just at "
        "the extremes.",
        transform=ax.transAxes, fontsize=8.7, color=MUTED, style="italic", ha="left", va="top", wrap=True,
    )
    fig.tight_layout(rect=[0, 0.1, 1, 0.98])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "concept_scale_comparison.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2. Real attack output -- value recovery
# ---------------------------------------------------------------------------

def _run_workload_in_memory(lab_orders: pd.DataFrame, approach: str, ratio: float | None, scale: int, n_queries: int = 300):
    key = encryption.derive_token_key("lab_orders" if approach == "D" else None)
    recs = records.prepare_records(lab_orders, approach, "lab_orders", config.SENSITIVE_FIELD, ratio)
    by_token = defaultdict(list)
    for r in recs:
        by_token[r.token].append(r)

    queries = workload.load_or_generate_workload(
        lab_orders, scale, sensitive_field=config.SENSITIVE_FIELD, n_queries=n_queries, label="concept_attack_demo",
    )
    value_counts = lab_orders[config.SENSITIVE_FIELD].astype(str).value_counts().to_dict()

    executed = []
    for value in queries:
        token = encryption.deterministic_token(value, key=key)
        executed.append(ExecutedQuery(true_value=value, token=token, volume=len(by_token.get(token, []))))
    return executed, value_counts


def plot_attack_value_output(scale: int = 1_000) -> None:
    df, _ = dataset.load_scaled_dataset(scale)
    lab_orders = schema.build_lab_orders(df)

    b_executed, value_counts = _run_workload_in_memory(lab_orders, "B", None, scale)
    d_executed, _ = _run_workload_in_memory(lab_orders, "D", 1.0, scale)

    b_rows = sorted(token_guess_table("B", b_executed, value_counts), key=lambda r: -r.observed_volume)[:8]
    d_rows = sorted(token_guess_table("D", d_executed, value_counts), key=lambda r: -r.observed_volume)[:8]

    b_correct = sum(1 for r in b_rows) and sum(r.correct for r in b_rows) / len(b_rows)
    d_correct = sum(1 for r in d_rows) and sum(r.correct for r in d_rows) / len(d_rows)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    fig.patch.set_facecolor(SURFACE)

    for ax, rows, acc, color in [
        (axes[0], b_rows, b_correct, LEAK),
        (axes[1], d_rows, d_correct, SAFE),
    ]:
        cell_rows = [
            [_short(r.token, 12), str(r.observed_volume), r.guessed_value[:22], r.true_value[:22], "correct" if r.correct else "wrong"]
            for r in rows
        ]
        colors = [[SURFACE] * 4 + [SAFE if r.correct else LEAK] for r in rows]
        tbl = _table(ax, ["token", "volume", "attacker's guess", "actual value", "result"], cell_rows, cell_colors=colors, col_widths=[0.16, 0.1, 0.32, 0.32, 0.16], fontsize=8.3)
        for (r, c), cell in tbl.get_celld().items():
            if r > 0 and c == 4:
                cell.set_text_props(color="white", fontweight="bold")
            if r == 0:
                cell.set_facecolor(color)
                cell.set_text_props(color="white", fontweight="bold")
        ax.text(
            0.0, -0.06,
            f"{acc:.0%} of these rows correct",
            transform=ax.transAxes, color=color, fontsize=9, fontweight="bold", ha="left", va="top",
        )

    fig.text(
        0.02, 0.01,
        "Left = Approach B (no decoys). Right = Approach D (decoy_target_ratio=1.0). Every row above is the literal "
        "output of the value-recovery attack (attack.token_guess_table), not a mock-up: the attacker sees only the "
        "token and how many records it returned, and guesses the value whose known real-world frequency is closest.",
        fontsize=8.5, color=MUTED, style="italic", ha="left", va="bottom", wrap=True,
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.98])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "concept_attack_value_output.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3. Real attack output -- linkage
# ---------------------------------------------------------------------------

def plot_attack_linkage_output(scale: int = 1_000, n_patients: int = 5) -> None:
    df, _ = dataset.load_scaled_dataset(scale)
    collections_df = schema.build_collections(df)

    b_records = {name: records.prepare_records(collections_df[name], "B", name, schema.QUERY_FIELD.get(name, config.SENSITIVE_FIELD)) for name in ["patients", "billing"]}
    d_records = {name: records.prepare_records(collections_df[name], "D", name, schema.QUERY_FIELD.get(name, config.SENSITIVE_FIELD)) for name in ["patients", "billing"]}

    b_link = run_linkage_attack("B", b_records)
    d_link = run_linkage_attack("D", d_records)

    b_patients_map = {r.plain_patient_code: r.patient_token for r in b_records["patients"] if not r.is_dummy}
    b_billing_map = {r.plain_patient_code: r.patient_token for r in b_records["billing"] if not r.is_dummy}
    d_patients_map = {r.plain_patient_code: r.patient_token for r in d_records["patients"] if not r.is_dummy}
    d_billing_map = {r.plain_patient_code: r.patient_token for r in d_records["billing"] if not r.is_dummy}

    shared_codes = list(set(b_patients_map) & set(b_billing_map))[:n_patients]

    rows = []
    for code in shared_codes:
        b_match = b_patients_map[code] == b_billing_map.get(code)
        d_match = d_patients_map.get(code) == d_billing_map.get(code)
        rows.append(
            [
                code,
                _short(b_patients_map.get(code), 10), _short(b_billing_map.get(code), 10), "LINKED" if b_match else "not linked",
                _short(d_patients_map.get(code), 10), _short(d_billing_map.get(code), 10), "LINKED" if d_match else "not linked",
            ]
        )

    fig, ax = plt.subplots(figsize=(15, 1.7 + 0.55 * len(rows)))
    fig.patch.set_facecolor(SURFACE)
    colors = []
    for r in rows:
        b_ok, d_ok = r[3] == "LINKED", r[6] == "LINKED"
        colors.append([SURFACE, SURFACE, SURFACE, LEAK if b_ok else SAFE, SURFACE, SURFACE, SAFE if not d_ok else LEAK])
    tbl = _table(
        ax,
        ["patient_code\n(ground truth)", "patients token (B)", "billing token (B)", "attacker's verdict (B)",
         "patients token (D)", "billing token (D)", "attacker's verdict (D)"],
        rows, cell_colors=colors, col_widths=[0.12, 0.15, 0.15, 0.16, 0.15, 0.15, 0.16], fontsize=8.3,
    )
    for (r, c), cell in tbl.get_celld().items():
        if r > 0 and c in (3, 6):
            cell.set_text_props(color="white", fontweight="bold")
    fig.text(
        0.02, 0.01,
        "The attacker's only signal is whether the same patient's token is identical across collections. "
        f"Measured across all patients this scale: B links {b_link.linkage_recovery_accuracy:.0%}, D links {d_link.linkage_recovery_accuracy:.0%}.",
        fontsize=8.5, color=MUTED, style="italic", ha="left", va="bottom", wrap=True,
    )
    fig.tight_layout(rect=[0, 0.1, 1, 0.98])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "concept_attack_linkage_output.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    plot_scale_comparison()
    plot_attack_value_output()
    plot_attack_linkage_output()
    print(f"Wrote figures to {FIG_DIR}/concept_*.png")


if __name__ == "__main__":
    main()
