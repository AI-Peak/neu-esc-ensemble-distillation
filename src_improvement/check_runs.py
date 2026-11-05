"""Technical acceptance of finished runs. Deliberately never compares scores with Table 6.

    python src_improvement/check_runs.py runs/ --seeds 42
    python src_improvement/check_runs.py runs/vsfc --dataset vsfc --setups mtl mtl_smart mtl_ed --seeds 42

A run passes when it finished on the benchmark protocol, trained (finite loss that went down,
validation macro-F1 above a constant majority-class predictor) and saved complete, unique
predictions. All runs must also come from one runner version. Exit code 1 if anything fails.
Closeness to the paper is not a criterion: a run far from Table 6 is a reason to look for bugs,
never to change the protocol for the remaining seeds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

BACKBONES = ("phobert", "visobert")
SETUPS = ("st_sentiment", "st_topic", "mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed")
TASKS = {"st_sentiment": ("sentiment",), "st_topic": ("topic",),
         "mtl": ("sentiment", "topic"), "mtl_smart": ("sentiment", "topic"),
         "mtl_mlm": ("sentiment", "topic"), "mtl_mlm_smart": ("sentiment", "topic"),
         "mtl_ed": ("sentiment", "topic")}
SPLIT_SIZES = {"neu": {"val": 3305, "test": 6613}, "vsfc": {"val": 1583, "test": 3166}}


def majority_macro_f1(labels, num_classes):
    """Macro-F1 of always predicting the most frequent class: F1 = 2p / (1 + p) on that class, 0 elsewhere."""
    p = np.bincount(labels, minlength=num_classes).max() / len(labels)
    return 2 * p / (1 + p) / num_classes


def check_run(run_dir, setup, dataset):
    problems = []
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return ["no metrics.json (run did not finish)"], None
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if metrics.get("status") != "COMPLETED":
        problems.append(f"status {metrics.get('status')}")
    if not metrics.get("benchmark_eligible"):
        problems.append("smoke/debug run (benchmark_eligible=false)")

    epochs = [json.loads(line) for line in (run_dir / "epochs.jsonl").read_text(encoding="utf-8").splitlines()]
    losses = [e["train_loss"] for e in epochs]
    if not all(math.isfinite(x) for x in losses):
        problems.append("non-finite training loss")
    elif len(losses) > 1 and not losses[-1] < losses[0]:
        problems.append(f"training loss did not go down ({losses[0]:.4f} -> {losses[-1]:.4f})")

    arrays = np.load(run_dir / "logits.npz")
    for task in TASKS[setup]:
        for split in ("val", "test"):
            if not np.isfinite(arrays[f"{split}_{task}"]).all():
                problems.append(f"non-finite {split} logits for {task}")
        labels = arrays[f"val_labels_{task}"]
        trivial = majority_macro_f1(labels, arrays[f"val_{task}"].shape[1])
        score = metrics["val"][task]["macro_f1"]
        if not score > trivial:
            problems.append(f"{task} val macro-F1 {score:.4f} <= majority-class {trivial:.4f}")

    with open(run_dir / "predictions.csv", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    ids = [r["sample_id"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate sample IDs in predictions.csv")
    if config.get("dataset", "neu") != dataset:
        problems.append(f"dataset {config.get('dataset', 'neu')}, expected {dataset}")
    for split, size in SPLIT_SIZES[dataset].items():
        count = sum(r["split"] == split for r in rows)
        if count != size:
            problems.append(f"{count} {split} predictions, expected {size}")
    return problems, config.get("code", {}).get("runner_sha256")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int, required=True, help="seeds that must be complete")
    parser.add_argument("--backbones", nargs="+", default=list(BACKBONES), choices=BACKBONES)
    parser.add_argument("--setups", nargs="+", default=list(SETUPS), choices=SETUPS)
    parser.add_argument("--dataset", default="neu", choices=list(SPLIT_SIZES))
    args = parser.parse_args(argv)

    found = {}
    for directory in args.run_dirs:
        for path in Path(directory).glob("*/config.json"):
            found.setdefault(path.parent.name, path.parent)

    failed, versions = 0, {}
    for seed in args.seeds:
        for backbone in args.backbones:
            for setup in args.setups:
                name = f"{backbone}-{setup}-s{seed}"
                if args.dataset != "neu":
                    name = f"{args.dataset}-{name}"
                if name not in found:
                    problems, sha = ["missing run directory"], None
                else:
                    problems, sha = check_run(found[name], setup, args.dataset)
                if sha:
                    versions.setdefault(sha, []).append(name)
                failed += bool(problems)
                print(f"{'PASS' if not problems else 'FAIL'}  {name:<28} {'; '.join(problems)}")

    if len(versions) > 1:
        failed += 1
        print("FAIL  runner versions differ: " + ", ".join(f"{sha[:12]} ({len(v)} runs)" for sha, v in versions.items()))
    elif versions:
        print(f"runner version {next(iter(versions))[:12]} for all runs")
    total = len(args.seeds) * len(args.backbones) * len(args.setups)
    if failed:
        print(f"{failed} problem(s): fix or rerun before using these results")
    else:
        print(f"all {total} runs pass")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
