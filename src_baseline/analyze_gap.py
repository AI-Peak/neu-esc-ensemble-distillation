"""Why do the reproduced numbers differ from Table 6? Tests each candidate cause on the runs.

    python src_baseline/analyze_gap.py

Inputs (run directories with metrics.json / logits.npz / config.json):
  runs/s42..s46        the original 40 runs (fp16, val selection)
  runs/gap/a           10 more seeds (47..56) of the 4 original setups with per-epoch test logits,
                       and the MLM rows (mtl_mlm, mtl_mlm_smart; seeds 42..46)
  runs/gap/mlm         the MLM rows for seeds 47..56, same runner and flags as runs/gap/a
  runs/gap/b           fp32 reruns of mtl / mtl_smart (seeds 42..46) and SMART with embedding noise
Prints the tables (markdown) and writes gap_runs.csv to --out; the write-up is
reports/baseline_reproduce/README.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

from aggregate import PAPER

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("sentiment", "topic")
GROUP = {"st_sentiment": "single", "st_topic": "single"}


def load_runs(folder, cohort):
    rows = []
    for metrics_path in sorted(Path(folder).glob("*/metrics.json")):
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics.get("status") != "COMPLETED":
            continue
        config = json.loads((metrics_path.parent / "config.json").read_text(encoding="utf-8"))
        setup = config["setup"]
        for task in metrics["test"]:
            rows.append({"cohort": cohort, "dir": metrics_path.parent, "backbone": config["backbone"],
                         "setup": setup, "group": GROUP.get(setup, setup), "task": task, "seed": config["seed"],
                         "precision": config["precision"], "best_epoch": metrics["best_epoch"],
                         "acc": 100 * metrics["test"][task]["accuracy"],
                         "mf1": 100 * metrics["test"][task]["macro_f1"]})
    return rows


def per_epoch(run_dir, task):
    """Test and val accuracy per epoch (None if the run did not log test per epoch)."""
    data = np.load(run_dir / "logits.npz")
    if f"test_by_epoch_{task}" not in data.files:
        return None
    test = (data[f"test_by_epoch_{task}"].argmax(-1) == data[f"test_labels_{task}"]).mean(1) * 100
    val = (data[f"val_by_epoch_{task}"].argmax(-1) == data[f"val_labels_{task}"]).mean(1) * 100
    return test, val


def fmt(values):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return "—"
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{values.mean():.2f} ± {values.std(ddof=1):.2f}"


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    from scipy import stats
    return float(stats.ttest_ind(a, b, equal_var=False).pvalue)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "reports" / "baseline_reproduce"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for seed in range(42, 47):
        rows += load_runs(ROOT / "runs" / f"s{seed}", "original")
    rows += load_runs(ROOT / "runs" / "gap" / "a", "more_seeds")
    rows += load_runs(ROOT / "runs" / "gap" / "mlm", "more_seeds")
    rows += load_runs(ROOT / "runs" / "gap" / "b", "wave_b")
    fp16 = [r for r in rows if r["precision"] != "fp32" and r["setup"] != "mtl_smart_emb"]
    lines = ["# Reproduction gap analysis", "",
             "Test accuracy in %. Paper = Table 6 (one run per row). fp16 runs with validation selection "
             "unless stated.", ""]

    # 1. Seed spread: is the paper inside the distribution of single runs?
    lines += ["## 1. Seed spread", "",
              "| Backbone | Setup | Task | n | mean ± std | min | max | Paper | Runs ≥ paper | z |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    summary = {}
    for (backbone, group), paper in PAPER.items():
        for task in TASKS:
            accs = [r["acc"] for r in fp16 if r["backbone"] == backbone and r["group"] == group and r["task"] == task]
            if not accs:
                continue
            accs = np.array(accs)
            ref = paper[task][0]
            sd = accs.std(ddof=1) if len(accs) > 1 else float("nan")
            z = (ref - accs.mean()) / sd if sd and not math.isnan(sd) else float("nan")
            summary[(backbone, group, task)] = (accs, ref)
            lines.append(f"| {backbone} | {group} | {task} | {len(accs)} | {fmt(accs)} | {accs.min():.2f} | "
                         f"{accs.max():.2f} | {ref:.2f} | {(accs >= ref).sum()}/{len(accs)} | {z:+.1f} |")
    lines.append("")

    # 2. Checkpoint selection (2-task runs that logged test accuracy every epoch).
    lines += ["## 2. Checkpoint selection (2-task, runs with per-epoch test)", "",
              "Val = our rule (best mean val macro-F1). Last = epoch 20. Test-picked = the one epoch with the "
              "best mean test accuracy over both tasks (what choosing a saved epoch by looking at test would "
              "give). Oracle = the best test epoch for that task alone, then the best seed (an upper bound no "
              "selection rule can beat). Best-of-seeds = the best single run under each rule.", "",
              "| Backbone | Setup | Task | n | Val | Last | Test-picked | Best-of-seeds (val) | "
              "Best-of-seeds (test-picked) | Oracle | Paper |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (backbone, group), paper in PAPER.items():
        if group == "single":
            continue
        dirs = sorted({r["dir"] for r in fp16 if r["backbone"] == backbone and r["group"] == group})
        curves = {}
        for d in dirs:
            got = {task: per_epoch(d, task) for task in TASKS}
            if all(v is not None for v in got.values()):
                curves[d] = got
        if not curves:
            continue
        for task in TASKS:
            val_sel, last, test_pick, oracle = [], [], [], []
            for d, got in curves.items():
                metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
                val_sel.append(100 * metrics["test"][task]["accuracy"])
                last.append(got[task][0][-1])
                joint = (got["sentiment"][0] + got["topic"][0]) / 2
                test_pick.append(got[task][0][int(joint.argmax())])
                oracle.append(got[task][0].max())
            lines.append(f"| {backbone} | {group} | {task} | {len(curves)} | {fmt(val_sel)} | {fmt(last)} | "
                         f"{fmt(test_pick)} | {max(val_sel):.2f} | {max(test_pick):.2f} | {max(oracle):.2f} | "
                         f"{paper[task][0]:.2f} |")
    lines.append("")

    # 3. Precision: fp32 (authors) vs fp16 (ours), same seeds.
    fp32 = [r for r in rows if r["precision"] == "fp32"]
    if fp32:
        lines += ["## 3. fp32 (authors' precision) vs fp16, same seeds", "",
                  "| Backbone | Setup | Task | n | fp16 | fp32 | Δ (paired) | Paper |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for (backbone, group), paper in PAPER.items():
            for task in TASKS:
                pairs = []
                for r in fp32:
                    if (r["backbone"], r["group"], r["task"]) != (backbone, group, task):
                        continue
                    match = [x for x in fp16 if (x["backbone"], x["setup"], x["task"], x["seed"]) ==
                             (backbone, r["setup"], task, r["seed"]) and x["cohort"] == "original"]
                    if match:
                        pairs.append((match[0]["acc"], r["acc"]))
                if pairs:
                    a, b = np.array(pairs).T
                    lines.append(f"| {backbone} | {group} | {task} | {len(pairs)} | {fmt(a)} | {fmt(b)} | "
                                 f"{(b - a).mean():+.2f} | {paper[task][0]:.2f} |")
        lines.append("")

    # 4. SMART with the bug fixed (noise on embeddings) vs the authors' token-ID SMART and plain MTL.
    emb = [r for r in rows if r["setup"] == "mtl_smart_emb"]
    if emb:
        lines += ["## 4. SMART with embedding noise (bug fixed) vs the authors' SMART", "",
                  "| Backbone | Task | n | MTL | SMART (author code) | SMART (embeddings) | Gain fixed − MTL | "
                  "Paper gain SMART − MTL | p (fixed vs MTL) |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for backbone in ("phobert", "visobert"):
            for task in TASKS:
                seeds = sorted({r["seed"] for r in emb if r["backbone"] == backbone})
                pick = lambda setup, src: [r["acc"] for r in src if r["backbone"] == backbone and r["setup"] == setup
                                           and r["task"] == task and r["seed"] in seeds and r["cohort"] != "more_seeds"]
                mtl, smart, fixed = pick("mtl", fp16), pick("mtl_smart", fp16), pick("mtl_smart_emb", emb)
                paper_gain = PAPER[(backbone, "mtl_smart")][task][0] - PAPER[(backbone, "mtl")][task][0]
                lines.append(f"| {backbone} | {task} | {len(fixed)} | {fmt(mtl)} | {fmt(smart)} | {fmt(fixed)} | "
                             f"{np.mean(fixed) - np.mean(mtl):+.2f} | {paper_gain:+.2f} | {welch(fixed, mtl):.3f} |")
        lines.append("")

    with open(out / "gap_runs.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cohort", "backbone", "setup", "task", "seed", "precision", "best_epoch", "acc", "mf1", "run"])
        for r in rows:
            writer.writerow([r["cohort"], r["backbone"], r["setup"], r["task"], r["seed"], r["precision"],
                             r["best_epoch"], f"{r['acc']:.4f}", f"{r['mf1']:.4f}", r["dir"].name])
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
