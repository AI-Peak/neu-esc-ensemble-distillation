"""Post-hoc logit bias for rare classes, chosen on validation and applied once to test. CPU only.

    python src_improvement/logit_bias.py --out reports/logit_bias

The prediction becomes argmax(logits + b). The bias maximises validation macro-F1 of that task; on a
tie the smallest |b| wins, so b = 0 is kept unless validation improves. Two variants, fixed in advance:
  rare  one bias on the sentiment class named in the draft (NEU: Toxic, UIT-VSFC: Neutral), grid -3..3 step 0.05
  full  one bias per class on either task, coordinate ascent from 0, two passes, grid -3..3 step 0.1
Every setup gets the same treatment, so ED + bias is compared with baseline + bias.

Runs come from the reports' per_run.csv. Before any bias, metrics recomputed from logits.npz must
match that file, otherwise the script stops.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import ttest_ind, ttest_rel

DATASETS = {
    "neu": {"report": "reports/improvement/per_run.csv",
            "dirs": ["runs/gap/f", "runs/s42", "runs/s43", "runs/s44", "runs/s45", "runs/s46", "runs/gap/a", "runs/gap/mlm"],
            "rare": 3, "rare_name": "Toxic", "seeds": 15},
    "vsfc": {"report": "reports/uit_vsfc/per_run.csv",
             "dirs": ["runs/vsfc/ed", "runs/vsfc/base", "runs/vsfc/mlm"],
             "rare": 1, "rare_name": "Neutral", "seeds": 10},
}
SETUPS = ("single", "mtl", "mtl_smart", "mtl_mlm", "mtl_mlm_smart", "mtl_ed")
TASKS = ("sentiment", "topic")


def scores(logits, labels, bias=None):
    """Accuracy and per-class F1 in %, with absent classes scored 0 like sklearn's zero_division=0."""
    n = logits.shape[1]
    pred = (logits if bias is None else logits + bias).argmax(1)
    tp = np.bincount(pred[pred == labels], minlength=n).astype(float)
    denom = np.bincount(pred, minlength=n) + np.bincount(labels, minlength=n)
    f1 = np.divide(2 * tp, denom, out=np.zeros(n), where=denom > 0)
    return 100 * float((pred == labels).mean()), 100 * f1


def macro(logits, labels, bias=None):
    return float(scores(logits, labels, bias)[1].mean())


def best_on_class(logits, labels, bias, cls, grid):
    """Best value of bias[cls] with the others fixed; ties go to the smallest |value|."""
    best_value, best_score = None, -1.0
    for value in sorted(grid, key=lambda v: (abs(v), v)):
        trial = bias.copy()
        trial[cls] = value
        score = macro(logits, labels, trial)
        if score > best_score + 1e-12:
            best_value, best_score = value, score
    return best_value


def fit_rare(logits, labels, cls):
    bias = np.zeros(logits.shape[1])
    bias[cls] = best_on_class(logits, labels, bias, cls, np.round(np.arange(-3, 3.0001, 0.05), 2))
    return bias


def fit_full(logits, labels):
    grid = np.round(np.arange(-3, 3.0001, 0.1), 1)
    bias = np.zeros(logits.shape[1])
    for _ in range(2):
        for cls in range(logits.shape[1]):
            bias[cls] = best_on_class(logits, labels, bias, cls, grid)
    return bias


def find_run(dirs, name):
    for directory in dirs:
        path = Path(directory) / name / "logits.npz"
        if path.exists():
            return path
        found = sorted(Path(directory).rglob(f"{name}/logits.npz"))
        if found:
            return found[0]
    raise FileNotFoundError(name)


def process(dataset, spec):
    rows = []
    with open(spec["report"], encoding="utf-8") as stream:
        for ref in csv.DictReader(stream):
            z = np.load(find_run(spec["dirs"], ref["run"]))
            task = ref["task"]
            val, val_y = z[f"val_{task}"], z[f"val_labels_{task}"]
            test, test_y = z[f"test_{task}"], z[f"test_labels_{task}"]
            acc0, f10 = scores(test, test_y)
            if abs(acc0 - float(ref["acc"])) > 1e-6 or abs(f10.mean() - float(ref["mf1"])) > 1e-6:
                raise SystemExit(f"{ref['run']} {task}: logits give {acc0}/{f10.mean()}, report has {ref['acc']}/{ref['mf1']}")
            variants = {"none": np.zeros(test.shape[1]), "full": fit_full(val, val_y)}
            if task == "sentiment":
                variants["rare"] = fit_rare(val, val_y, spec["rare"])
            for variant, bias in variants.items():
                acc, f1 = scores(test, test_y, bias)
                rows.append({"dataset": dataset, "backbone": ref["backbone"], "setup": ref["setup"], "task": task,
                             "seed": int(ref["seed"]), "variant": variant, "test_acc": acc, "test_mf1": float(f1.mean()),
                             "test_rare_f1": float(f1[spec["rare"]]) if task == "sentiment" else "",
                             "val_mf1": macro(val, val_y, bias), "bias": " ".join(f"{b:g}" for b in bias), "run": ref["run"]})
    return rows


def cell(values):
    return f"{np.mean(values):.2f} ± {np.std(values, ddof=1):.2f}"


def report(rows, out):
    data = defaultdict(dict)
    for r in rows:
        data[(r["dataset"], r["backbone"], r["setup"], r["task"], r["variant"])][r["seed"]] = r
    pick = lambda key, field: np.array([data[key][s][field] for s in sorted(data[key])], dtype=float)
    lines = ["# Logit bias chọn trên validation", "",
             "Test, mean ± std qua seed. `rare`: một bias trên lớp hiếm của sentiment. `full`: một bias cho mỗi lớp.",
             "Δ và p (t-test ghép cặp theo seed) so với cùng setup không có bias.", ""]
    for dataset, spec in DATASETS.items():
        for task in TASKS:
            variants = ("rare", "full") if task == "sentiment" else ("full",)
            for variant in variants:
                rare = task == "sentiment"
                lines += [f"## {dataset} / {task} / {variant}", "",
                          "| Backbone | Setup | n | Acc gốc | Acc bias | Δ (p) | mF1 gốc | mF1 bias | Δ (p) |"
                          + (f" F1 {spec['rare_name']} gốc | F1 bias | Δ (p) |" if rare else ""),
                          "|---|---|---:|---:|---:|---:|---:|---:|---:|" + ("---:|---:|---:|" if rare else "")]
                for backbone in ("phobert", "visobert"):
                    for setup in SETUPS:
                        base = (dataset, backbone, setup, task, "none")
                        key = (dataset, backbone, setup, task, variant)
                        if key not in data:
                            continue
                        line = f"| {backbone} | {setup} | {len(data[key])} |"
                        for field in ("test_acc", "test_mf1") + (("test_rare_f1",) if rare else ()):
                            a, b = pick(base, field), pick(key, field)
                            p = ttest_rel(b, a).pvalue if np.any(a != b) else float("nan")
                            line += f" {cell(a)} | {cell(b)} | {b.mean() - a.mean():+.2f} ({p:.3f}) |"
                        lines.append(line)
                lines += ["", f"ED + {variant} so với baseline + {variant} (Welch, Δ acc / Δ mF1):", "",
                          "| Backbone | Setup | Δ acc (p) | Δ mF1 (p) |", "|---|---|---:|---:|"]
                for backbone in ("phobert", "visobert"):
                    ed = (dataset, backbone, "mtl_ed", task, variant)
                    for setup in SETUPS[:-1]:
                        key = (dataset, backbone, setup, task, variant)
                        if key not in data:
                            continue
                        parts = []
                        for field in ("test_acc", "test_mf1"):
                            a, b = pick(key, field), pick(ed, field)
                            parts.append(f"{b.mean() - a.mean():+.2f} ({ttest_ind(b, a, equal_var=False).pvalue:.3f})")
                        lines.append(f"| {backbone} | {setup} | {parts[0]} | {parts[1]} |")
                lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="reports/logit_bias")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for dataset, spec in DATASETS.items():
        rows += process(dataset, spec)
        print(dataset, "checked and fitted", sum(r["dataset"] == dataset and r["variant"] == "none" for r in rows), "task runs")
    with open(out / "per_run.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report(rows, out)


if __name__ == "__main__":
    main()
