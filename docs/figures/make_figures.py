"""Builds the vector PDF figures of the paper from the per-run results in the repository.

    python docs/figures/make_figures.py

Run from the repository root. Accuracy and macro-F1 come from the tracked per_run.csv files. Per-class
F1 and the teacher scores come from runs/ (gitignored), which has to be on disk.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import stats

OUT = Path("Paper/figures")
BLUE, ORANGE = "#2a78d6", "#eb6834"  # first two categorical slots, checked with validate_palette
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
WIDTH = 5.17  # \textwidth of the template (372 pt), so the fonts below stay at their true size

plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42, "font.family": "DejaVu Sans", "font.size": 7.5,
    "axes.titlesize": 7.5, "axes.titleweight": "bold", "axes.labelsize": 7.5, "axes.edgecolor": MUTED,
    "axes.linewidth": 0.6, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK,
    "xtick.major.width": 0.6, "ytick.major.size": 0, "xtick.major.size": 2.5, "legend.frameon": False,
    "legend.fontsize": 7.5, "axes.spines.top": False, "axes.spines.right": False,
})

per = pd.read_csv("reports/improvement/per_run.csv")
vsfc = pd.read_csv("reports/uit_vsfc/per_run.csv")

SETUPS = [("single", "Single-task"), ("mtl", "MTL"), ("mtl_smart", "MTL + SMART"), ("mtl_mlm", "MTL + MLM"),
          ("mtl_mlm_smart", "MTL + MLM + SMART"), ("mtl_ed", "ED")]
REPORTED = {  # Table 6 of Mai et al. (sentiment, topic), one run per row
    ("phobert", "single"): (81.75, 78.65), ("phobert", "mtl"): (82.88, 79.25),
    ("phobert", "mtl_smart"): (83.26, 79.31), ("phobert", "mtl_mlm"): (82.67, 78.48),
    ("phobert", "mtl_mlm_smart"): (83.66, 79.49), ("visobert", "single"): (82.78, 77.94),
    ("visobert", "mtl"): (82.63, 78.56), ("visobert", "mtl_smart"): (83.58, 79.80),
    ("visobert", "mtl_mlm"): (82.23, 78.38), ("visobert", "mtl_mlm_smart"): (83.12, 79.25),
}


def seed_figure():
    """Box plots per setup, with the two backbones side by side and the reported single score as a diamond."""
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 3.15), sharex=True)
    series = (("phobert", "PhoBERT", BLUE, -0.2), ("visobert", "ViSoBERT", ORANGE, 0.2))
    for r, (task, title) in enumerate((("sentiment", "Sentiment"), ("topic", "Topic"))):
        ax = axes[r]
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.axvspan(len(SETUPS) - 1.5, len(SETUPS) - 0.5, color=GRID, alpha=0.55, lw=0, zorder=0)
        for bb, _, color, shift in series:
            for i, (setup, _) in enumerate(SETUPS):
                acc = per[(per.backbone == bb) & (per.setup == setup) & (per.task == task)].acc.values
                ax.boxplot(acc, positions=[i + shift], widths=0.32, patch_artist=True, manage_ticks=False,
                           boxprops=dict(facecolor=color, edgecolor=color, alpha=0.35, lw=0.8),
                           medianprops=dict(color=color, lw=1.6, solid_capstyle="butt"),
                           whiskerprops=dict(color=color, lw=0.8), capprops=dict(color=color, lw=0.8),
                           flierprops=dict(marker="o", ms=2.6, mfc=color, mec="none", alpha=0.8))
                if (bb, setup) in REPORTED:
                    ax.scatter(i + shift, REPORTED[(bb, setup)][r], s=17, marker="D", facecolor="white",
                               edgecolor=INK, lw=0.7, zorder=4)
        ax.set_title(title, loc="left", pad=3)
        ax.set_ylabel("Test accuracy (%)")
        ax.set_xlim(-0.5, len(SETUPS) - 0.5)
        ax.tick_params(axis="y", color=MUTED, labelcolor=MUTED, length=2.5, width=0.6, labelsize=7)
        ax.tick_params(axis="x", length=0)
    axes[1].set_xticks(range(len(SETUPS)))
    axes[1].set_xticklabels(["Single-task", "MTL", "MTL +\nSMART", "MTL +\nMLM", "MTL + MLM\n+ SMART", "ED"])
    handles = [Patch(facecolor=BLUE, edgecolor=BLUE, alpha=0.5, label="PhoBERT"),
               Patch(facecolor=ORANGE, edgecolor=ORANGE, alpha=0.5, label="ViSoBERT"),
               Line2D([], [], marker="D", ls="", ms=3.8, mfc="white", mec=INK, mew=0.7, label="Reported (one run)")]
    fig.legend(handles=handles, loc="upper right", ncol=3, bbox_to_anchor=(0.995, 1.0), handletextpad=0.4, columnspacing=1.2)
    fig.align_ylabels(axes)
    fig.tight_layout(rect=(0, 0, 1, 0.985), h_pad=0.6)
    fig.savefig(OUT / "fig_seed_distribution.pdf")
    plt.close(fig)


def per_class_table():
    idx = {}
    for root in ["runs/gap/f", "runs/s42", "runs/s43", "runs/s44", "runs/s45", "runs/s46", "runs/gap/a", "runs/gap/mlm"]:
        for folder in glob.glob(root + "/*"):
            if os.path.exists(folder + "/metrics.json"):
                idx.setdefault(os.path.basename(folder), folder)
    rows = []
    for _, row in per.iterrows():
        metrics = json.load(open(idx[row.run] + "/metrics.json"))
        test = metrics["test"][row.task]
        assert abs(test["accuracy"] * 100 - row.acc) < 1e-6
        for k, value in enumerate(test["per_class_f1"]):
            rows.append((row.backbone, row.setup, row.task, int(row.seed), k, value * 100))
    return pd.DataFrame(rows, columns="bb setup task seed cls f1".split())


def welch_ci(a, b):
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    return stats.t.ppf(0.975, df) * np.sqrt(va + vb)


def class_figure(table):
    groups = (
        ("sentiment", "Sentiment", [(0, "Neutral", 69.1), (2, "Negative", 15.7), (1, "Positive", 12.6), (3, "Toxic", 2.5)]),
        ("topic", "Topic", [(3, "Other", 43.7), (2, "Academic", 31.9), (4, "Service", 7.1), (6, "Personal Affairs", 4.5),
                            (1, "News", 2.7), (5, "Jobs & Recruitment", 2.4), (7, "Social Affairs", 2.3),
                            (8, "Help & Share", 2.0), (9, "Club & Events", 2.0), (0, "Spam", 1.2)]),
    )
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 2.75), sharex=True, gridspec_kw={"height_ratios": [4, 10]})
    series = (("phobert", "PhoBERT", BLUE, "o", 0.16), ("visobert", "ViSoBERT", ORANGE, "s", -0.16))
    for ax, (task, title, classes) in zip(axes, groups):
        ax.set_axisbelow(True)
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.axvline(0, color=MUTED, lw=0.8)
        for bb, _, color, marker, shift in series:
            for pos, (k, _, _) in enumerate(classes):
                y = len(classes) - 1 - pos + shift
                sel = table[(table.bb == bb) & (table.task == task) & (table.cls == k)]
                ed = sel[sel.setup == "mtl_ed"].f1.values
                base = sel[sel.setup == "mtl_smart"].f1.values
                delta = ed.mean() - base.mean()
                half = welch_ci(ed, base)
                ax.plot([delta - half, delta + half], [y, y], color=color, lw=0.9, solid_capstyle="round")
                ax.scatter(delta, y, s=15, marker=marker, color=color, edgecolor="white", lw=0.4, zorder=3)
        ax.set_yticks(range(len(classes)))
        ax.set_yticklabels([f"{name} ({share:.1f}%)" for _, name, share in classes][::-1])
        ax.set_ylim(-0.6, len(classes) - 0.4)
        ax.set_title(title, loc="left", pad=3)
    axes[1].set_xlabel("Change in test F1: ED minus MTL + SMART (points)")
    handles = [Line2D([], [], marker=m, ls="", ms=3.8, color=c, mec="white", mew=0.4, label=n) for _, n, c, m, _ in series]
    fig.legend(handles=handles, loc="upper right", ncol=2, bbox_to_anchor=(0.99, 1.0), handletextpad=0.2)
    fig.tight_layout(rect=(0, 0, 1, 0.985), h_pad=0.5)
    fig.savefig(OUT / "fig_perclass_delta.pdf")
    plt.close(fig)


def teacher_scores():
    scores = {}
    for name, root in (("neu", "runs/gap/c/*-f?of5"), ("vsfc", "runs/vsfc/teach/vsfc-*-f?of5")):
        folders = glob.glob(root)
        assert len(folders) == 30
        scores[name] = {}
        for task in ("sentiment", "topic"):
            probs = []
            for folder in folders:
                data = np.load(folder + "/logits.npz")
                logits, labels = data[f"test_{task}"], data[f"test_labels_{task}"]
                p = np.exp(logits - logits.max(1, keepdims=True))
                probs.append(p / p.sum(1, keepdims=True))
            scores[name][task] = (np.mean(probs, 0).argmax(1) == labels).mean() * 100
    return scores


def gap_figure(scores):
    rows = []
    for ds, frame in (("neu", per), ("vsfc", vsfc)):
        for bb in ("phobert", "visobert"):
            for task in ("sentiment", "topic"):
                sel = frame[(frame.backbone == bb) & (frame.task == task)]
                mtl, ed = sel[sel.setup == "mtl"].acc.mean(), sel[sel.setup == "mtl_ed"].acc.mean()
                rows.append((ds, bb, task, scores[ds][task] - mtl, ed - mtl))
    data = pd.DataFrame(rows, columns="ds bb task gap gain".split())
    r, p = stats.pearsonr(data.gap, data.gain)
    print(data.round(2).to_string(), f"\npearson r={r:.3f} p={p:.4f}")

    fig, ax = plt.subplots(figsize=(WIDTH, 2.0))
    ax.set_axisbelow(True)
    ax.grid(color=GRID, lw=0.5)
    ax.plot([-0.25, 1.75], [-0.25, 1.75], color=MUTED, lw=0.8, ls=(0, (4, 3)))
    ax.text(0.27, 0.40, "ED equals the teacher", color=MUTED, rotation=27, fontsize=7, ha="center", va="center")
    colors = {"neu": BLUE, "vsfc": ORANGE}
    markers = {"sentiment": "o", "topic": "s"}
    names = {"phobert": "PhoBERT", "visobert": "ViSoBERT"}
    offset = {("neu", "phobert", "sentiment"): (-5, 2, "right"), ("neu", "phobert", "topic"): (5, -5, "left"),
              ("neu", "visobert", "sentiment"): (5, -6, "left"), ("neu", "visobert", "topic"): (-5, 3, "right"),
              ("vsfc", "phobert", "sentiment"): (8, -10, "left"), ("vsfc", "phobert", "topic"): (-5, 3, "right"),
              ("vsfc", "visobert", "sentiment"): (5, -6, "left"), ("vsfc", "visobert", "topic"): (5, -5, "left")}
    for _, row in data.iterrows():
        ax.scatter(row.gap, row.gain, s=26, color=colors[row.ds], marker=markers[row.task], edgecolor="white", lw=0.5, zorder=3)
        dx, dy, ha = offset[(row.ds, row.bb, row.task)]
        ax.annotate(f"{names[row.bb]} {row.task}", (row.gap, row.gain), xytext=(dx, dy), textcoords="offset points",
                    fontsize=6.5, color=INK, ha=ha)
    ax.set_xlim(-0.25, 2.75)
    ax.set_ylim(-0.12, 1.75)
    ax.set_xlabel("Teacher gap: 30-model ensemble minus MTL (accuracy points)")
    ax.set_ylabel("ED gain: ED minus MTL\n(accuracy points)")
    ax.tick_params(axis="y", color=MUTED, labelcolor=MUTED, length=2.5, width=0.6)
    handles = [Line2D([], [], marker="o", ls="", ms=4.5, color=BLUE, mec="white", label="NEU-ESC"),
               Line2D([], [], marker="o", ls="", ms=4.5, color=ORANGE, mec="white", label="UIT-VSFC"),
               Line2D([], [], marker="o", ls="", ms=4.5, color=MUTED, mec="white", label="Sentiment"),
               Line2D([], [], marker="s", ls="", ms=4.5, color=MUTED, mec="white", label="Topic")]
    ax.legend(handles=handles, loc="lower right", ncol=2, handletextpad=0.2, columnspacing=1.0)
    fig.tight_layout(pad=0.4)
    fig.savefig("docs/figures/fig_gap_gain.pdf")  # not used in the paper
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    seed_figure()
    table = per_class_table()
    class_figure(table)
    gap_figure(teacher_scores())
    # Teacher probability on the rare sentiment class, for the rows that carry that label
    for name, targets, csv, rare in (("NEU-ESC Toxic", "runs/gap/c/ens_targets.npz", "data/NEU/train_set.csv", 3),
                                     ("UIT-VSFC Neutral", "runs/vsfc/teach/ens_targets_vsfc.npz", "data/UIT-VSFC/train_set.csv", 1)):
        z = np.load(targets)
        labels = pd.read_csv(csv).sentiment.values
        q = z["sentiment"]
        print(name, "rows", (labels == rare).sum(), "mean q(rare | label rare)", round(q[labels == rare, rare].mean(), 3),
              "teacher recall", round((q[labels == rare].argmax(1) == rare).mean() * 100, 1),
              "share of rows the teacher assigns to rare", round((q.argmax(1) == rare).mean() * 100, 2),
              "label share", round((labels == rare).mean() * 100, 2))


if __name__ == "__main__":
    main()
