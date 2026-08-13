"""Four figures, one per approach (A/B/C/D), each showing several real example records so
the reader can compare *how the same underlying data actually looks* under each approach --
plaintext vs. token, and real-only vs. real+decoy -- rather than one record in isolation.

All four figures carry the *same* underlying group of records (every `lab_orders` row for
one real `specific_diagnostic_test` value) through that approach's transformation, so the
"before" state in each figure is the same real data, and the group is directly comparable
figure-to-figure: A shows it in the clear; B shows it encrypted (and because every row here
shares one real value, every token is identical -- the leak, made concrete); C/D show the
same encrypted group after decoys are mixed in, indistinguishable server-side, with a
research-only "ground truth" column revealing which the attacker's realism filter can and
can't tell apart.

Usage:
    python -m src.analysis.generate_approach_examples

Produces:
    results/figures/approach_A_example.png
    results/figures/approach_B_example.png
    results/figures/approach_C_example.png
    results/figures/approach_D_example.png
"""
from __future__ import annotations

import os
import textwrap

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

from src.core import config, dataset, decoys, records, schema
from src.analysis.generate_report import FIG_DIR, GRID, INK, MUTED, SURFACE

LEAK = "#c1352b"
SAFE = "#1baf7a"
NOTE = "#c9a227"
REAL_BG = "#eef7f2"
DECOY_BG = "#fbf3e3"

MAX_DECOYS_SHOWN = 3


def _short(b: bytes | None, n: int = 18) -> str:
    return (b.hex()[:n] + "...") if b else "-"


def _short_id(record_id: str, n: int = 12) -> str:
    return record_id if len(record_id) <= n + 3 else record_id[:n] + "..."


def _wrapped_suptitle(fig, text: str, width: int = 100, **kwargs) -> None:
    wrapped = "\n".join(textwrap.fill(line, width=width) for line in text.split("\n"))
    fig.suptitle(wrapped, **kwargs)


def _pick_example_value(lab_orders: pd.DataFrame) -> str:
    vc = lab_orders[config.SENSITIVE_FIELD].astype(str).value_counts()
    candidates = vc[(vc >= 4) & (vc <= 7)]
    return candidates.index[0] if not candidates.empty else vc.index[-1]


def _build_context():
    df, _ = dataset.load_scaled_dataset(1_000)
    lab_orders = schema.build_lab_orders(df)
    value = _pick_example_value(lab_orders)
    real_rows = lab_orders[lab_orders[config.SENSITIVE_FIELD] == value].reset_index(drop=True)
    companion_fields = schema.COMPANION_FIELDS.get("lab_orders", [])
    joint_dist = decoys.build_joint_distribution(lab_orders, config.SENSITIVE_FIELD, companion_fields)
    return lab_orders, value, real_rows, companion_fields, joint_dist


def _table(ax, col_labels, cell_rows, cell_colors=None, col_widths=None, fontsize=9.5):
    ax.axis("off")
    tbl = ax.table(
        cellText=cell_rows, colLabels=col_labels, cellColours=cell_colors,
        colWidths=col_widths, loc="upper left", cellLoc="left", bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(fontsize)
    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor(GRID)
        if row == 0:
            cell.set_text_props(fontweight="bold", color=INK)
            cell.set_facecolor("#f0efe9")
    return tbl


# ---------------------------------------------------------------------------
# Approach A -- plaintext
# ---------------------------------------------------------------------------

def plot_approach_A(lab_orders, value, real_rows) -> None:
    n = min(len(real_rows), 6)
    rows = [
        [
            real_rows.iloc[i]["record_id"],
            str(real_rows.iloc[i][config.LINK_FIELD]),
            real_rows.iloc[i][config.SENSITIVE_FIELD],
            real_rows.iloc[i]["diagnostic_test_category"],
        ]
        for i in range(n)
    ]

    fig, ax = plt.subplots(figsize=(11, 1.1 + 0.55 * n))
    fig.patch.set_facecolor(SURFACE)
    _table(
        ax, ["record_id", "patient_code", "specific_diagnostic_test", "diagnostic_test_category"],
        rows, col_widths=[0.16, 0.14, 0.42, 0.28],
    )
    ax.text(
        0.0, -0.06,
        f"{n} example lab_orders records, all sharing the real value '{value}' — stored and returned exactly as-is. "
        "An observing server (or anyone with read access) sees every field in the clear -- the sensitive value, "
        "who it belongs to, and that these records are related, with no effort at all.",
        transform=ax.transAxes, fontsize=8.5, color=LEAK, style="italic", ha="left", va="top", wrap=True,
    )
    fig.tight_layout(rect=[0, 0.02, 1, 0.98])
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "approach_A_example.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Approach B -- deterministic encryption
# ---------------------------------------------------------------------------

def plot_approach_B(lab_orders, value, real_rows) -> None:
    b_records = {r.record_id: r for r in records.prepare_records(lab_orders, "B", "lab_orders", config.SENSITIVE_FIELD)}
    n = min(len(real_rows), 6)
    after = [b_records[real_rows.iloc[i]["record_id"]] for i in range(n)]
    tokens = {_short(r.token) for r in after}

    fig = plt.figure(figsize=(11, 1.8 + 0.55 * n))
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.1, 0.35, n * 0.55 + 0.6], hspace=0.35)

    ax_before = fig.add_subplot(gs[0])
    ax_before.axis("off")
    ax_before.text(0.0, 1.0, "BEFORE (plaintext)", fontsize=10, fontweight="bold", color=MUTED, va="top")
    ax_before.text(0.0, 0.55, f"specific_diagnostic_test = \"{value}\"   (appears in all {n} records below)", fontsize=9.5, family="monospace", color=INK, va="top")
    ax_before.text(0.5, 0.05, "-- AES-SIV, deterministic --->", fontsize=9, color=MUTED, ha="center", va="top", style="italic")

    ax_note = fig.add_subplot(gs[1])
    ax_note.axis("off")
    same_token = len(tokens) == 1
    note = (
        f"AFTER: every record below gets the SAME token ({next(iter(tokens))}) because they all share the same "
        "plaintext value and the same encryption key. The value itself is hidden, but the fact that these N "
        "records are all the same value is not -- that repetition is exactly what the value-recovery attack exploits."
        if same_token else "AFTER (tokens should match here; showing observed values):"
    )
    ax_note.text(0.0, 0.5, note, fontsize=8.7, color=LEAK, style="italic", va="center", wrap=True)

    ax_after = fig.add_subplot(gs[2])
    rows = [[r.record_id, _short(r.token), _short(r.patient_token)] for r in after]
    _table(ax_after, ["record_id", "token (specific_diagnostic_test)", "patient_token"], rows, col_widths=[0.18, 0.42, 0.4])

    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, "approach_B_example.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Approach C / D -- naive / generative decoys (shared layout, different generator)
# ---------------------------------------------------------------------------

def _plausibility(sample_records, joint_dist, companion_fields):
    rows = [{config.SENSITIVE_FIELD: r.plain_value, **(r.companion_values or {})} for r in sample_records]
    return decoys.realism_filter(rows, joint_dist, config.SENSITIVE_FIELD, companion_fields, threshold=1e-6)


def _plot_decoy_approach(approach: str, subtitle_extra: str, lab_orders, value, real_rows, companion_fields, joint_dist) -> None:
    all_records = records.prepare_records(lab_orders, approach, "lab_orders", config.SENSITIVE_FIELD, decoy_target_ratio=1.0)
    group = [r for r in all_records if r.plain_value == value]
    real = [r for r in group if not r.is_dummy]
    decoy = [r for r in group if r.is_dummy][:MAX_DECOYS_SHOWN]
    n_decoys_total = sum(1 for r in group if r.is_dummy)

    sample = real + decoy
    plausible = _plausibility(sample, joint_dist, companion_fields)

    n_before = len(real)
    n = len(sample)

    fig = plt.figure(figsize=(12.5, 2.0 + 0.55 * n))
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 0.35, n * 0.55 + 0.7], hspace=0.35)

    ax_before = fig.add_subplot(gs[0])
    ax_before.axis("off")
    ax_before.text(0.0, 1.0, "BEFORE decoys (encrypted, real records only)", fontsize=10, fontweight="bold", color=MUTED, va="top")
    ax_before.text(
        0.0, 0.5,
        f"{n_before} real record(s) for '{value}', all sharing one token — identical to Approach B's output at this point.",
        fontsize=9, color=INK, va="top",
    )
    ax_before.text(0.5, 0.05, f"-- pad to flatten frequency (ratio=1.0): {n_decoys_total} decoys generated for this value, {len(decoy)} shown --->",
                   fontsize=8.7, color=MUTED, ha="center", va="top", style="italic")

    ax_note = fig.add_subplot(gs[1])
    ax_note.axis("off")
    ax_note.text(
        0.0, 0.5,
        textwrap.fill(
            "AFTER: real and decoy records share the same id space and the same token — the server cannot "
            "tell them apart. The columns below marked 'research only' are ground truth we hold as "
            "researchers to score the attack; the server (and the attacker) never sees them. "
            + subtitle_extra,
            width=118,
        ),
        fontsize=8.7, color=MUTED, style="italic", va="center",
    )

    ax_after = fig.add_subplot(gs[2])
    headers = ["record_id", "token", "diagnostic_test_category\n(encrypted payload)", "ground truth\n(research only)", "realism filter\n(research only)"]
    rows, colors = [], []
    for r, ok in zip(sample, plausible):
        kind = "real" if not r.is_dummy else "decoy"
        companion = (r.companion_values or {}).get("diagnostic_test_category", "-")
        flag = "PASS (looks real)" if ok else "FAIL (looks fake)"
        rows.append([_short_id(r.record_id), _short(r.token), companion, kind, flag])
        row_bg = REAL_BG if not r.is_dummy else DECOY_BG
        flag_color = SAFE if ok else LEAK
        colors.append([row_bg, row_bg, row_bg, row_bg, flag_color])
    tbl = _table(ax_after, headers, rows, cell_colors=[[c for c in row] for row in colors], col_widths=[0.16, 0.24, 0.24, 0.15, 0.21])
    for (r, c), cell in tbl.get_celld().items():
        if r > 0 and c == 4:
            cell.set_text_props(color="white", fontweight="bold")

    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.savefig(os.path.join(FIG_DIR, f"approach_{approach}_example.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_approach_C(lab_orders, value, real_rows, companion_fields, joint_dist) -> None:
    _plot_decoy_approach(
        "C",
        "Decoys sample each field independently, so their field combinations often look implausible — an attacker's realism filter can strip most of them out.",
        lab_orders, value, real_rows, companion_fields, joint_dist,
    )


def plot_approach_D(lab_orders, value, real_rows, companion_fields, joint_dist) -> None:
    _plot_decoy_approach(
        "D",
        "Decoys' companion fields are sampled from the real conditional distribution, so they pass the same realism filter that catches Approach C's decoys.",
        lab_orders, value, real_rows, companion_fields, joint_dist,
    )


def main():
    lab_orders, value, real_rows, companion_fields, joint_dist = _build_context()
    print(f"Example value: '{value}' ({len(real_rows)} real records in lab_orders)")
    plot_approach_A(lab_orders, value, real_rows)
    plot_approach_B(lab_orders, value, real_rows)
    plot_approach_C(lab_orders, value, real_rows, companion_fields, joint_dist)
    plot_approach_D(lab_orders, value, real_rows, companion_fields, joint_dist)
    print(f"Wrote figures to {FIG_DIR}/approach_[A-D]_example.png")


if __name__ == "__main__":
    main()
