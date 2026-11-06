"""Audit all 30 OOF teachers and reconstruct target probabilities before student training."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inference.registry import sha256


def validate_targets(targets, runs, dataset):
    import numpy as np
    from src_improvement.neu_esc_improvement import BACKBONES, DATASETS, FOLD_SEED, fold_rows

    spec = DATASETS[dataset]
    n = spec["split_sizes"]["train"]
    classes = spec["num_labels"]
    expected = {(b, s, f) for b in BACKBONES for s in (42, 43, 44) for f in range(5)}
    found, sources, target_dtypes = set(), [], {}
    counts = np.zeros(n, dtype=np.int64)
    sums = {t: np.zeros((n, classes[t]), dtype=np.float64) for t in classes}
    with np.load(targets, allow_pickle=False) as target:
        if str(target["train_csv_sha256"]) != spec["files"]["train_set.csv"]:
            raise ValueError("target train hash differs from pinned raw CSV")
        names = [str(x) for x in target["sources"]]
        if len(names) != 30 or len(set(names)) != 30:
            raise ValueError("exactly 30 distinct teacher sources are required")
        if len(runs) != 30:
            raise ValueError("pass all 30 source run directories")
        runs_by_name = {Path(run).name: Path(run) for run in runs}
        if set(runs_by_name) != set(names):
            raise ValueError("source run directory names must match the 30 archived sources")
        # Floating point addition depends on order. Reconstruct in the recorded assembly
        # order even when recovered directories are passed in a different CLI order.
        for name in names:
            run = runs_by_name[name]
            config = json.loads((run / "config.json").read_text(encoding="utf-8"))
            metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
            fold = config.get("fold") or {}
            key = config.get("backbone"), config.get("seed"), fold.get("fold")
            if key not in expected or key in found:
                raise ValueError(f"unexpected/duplicate backbone, seed or fold: {run}")
            found.add(key)
            backbone = BACKBONES[key[0]]
            train_name = "train_set_processed.csv" if backbone["processed"] else "train_set.csv"
            expected_data = {f"{s}_set{'_processed' if backbone['processed'] else ''}.csv":
                             spec["files"][f"{s}_set{'_processed' if backbone['processed'] else ''}.csv"]
                             for s in ("train", "val", "test")}
            if (config.get("dataset") != dataset or config.get("setup") != "mtl"
                    or config.get("revision") != backbone["revision"] or config.get("model_path_override")
                    or config.get("data_files") != expected_data
                    or config.get("tasks") != ["sentiment", "topic"]
                    or config.get("selection") != "mean val macro-F1 over both tasks"
                    or config.get("max_steps_per_epoch") or config.get("limit_eval")
                    or config.get("epochs") != 20 or not config.get("benchmark_eligible")
                    or metrics.get("status") != "COMPLETED" or not metrics.get("benchmark_eligible")
                    or not isinstance(metrics.get("best_epoch"), int)
                    or metrics.get("runner_sha256") != config.get("code", {}).get("runner_sha256")
                    or fold.get("num_folds") != 5 or fold.get("fold_seed") != FOLD_SEED
                    or run.name not in names):
                raise ValueError(f"invalid teacher training/selection provenance: {run}")
            with np.load(run / "oof.npz", allow_pickle=False) as oof:
                rows = oof["rows"]
                held_out = fold_rows(n, key[2], 5)
                if (str(oof["train_csv_sha256"]) != spec["files"][train_name]
                        or rows.dtype.kind not in "iu" or not np.array_equal(rows, held_out)
                        or fold.get("held_out_rows") != len(held_out)):
                    raise ValueError(f"OOF row coverage or train hash mismatch: {run}")
                for task in classes:
                    logits = oof[f"oof_{task}"].astype(np.float64)
                    if logits.shape != (len(rows), classes[task]) or not np.isfinite(logits).all():
                        raise ValueError(f"invalid OOF logits: {run}/{task}")
                    probs = np.exp(logits - logits.max(1, keepdims=True))
                    sums[task][rows] += probs / probs.sum(1, keepdims=True)
                counts[rows] += 1
            sources.append(dict(run_name=run.name, backbone=key[0], seed=key[1], fold=key[2],
                                hashes={name: sha256(run / name) for name in ("config.json", "metrics.json", "oof.npz")}))
        if found != expected or not np.all(counts == 6) or not np.array_equal(target["counts"], counts):
            raise ValueError("each raw train row must have exactly six held-out predictions")
        for task in classes:
            probabilities = target[task]
            if (probabilities.dtype not in (np.dtype("float16"), np.dtype("float32"))
                    or probabilities.shape != (n, classes[task]) or not np.isfinite(probabilities).all()
                    or np.any(probabilities < 0) or np.any(probabilities > 1)):
                raise ValueError(f"target probabilities fail reconstruction: {task}")
            # ensemble_targets assembles softmax means in float64, then stores float32.
            # Historical archives additionally cast those arrays to float16. Reproduce
            # those casts exactly: acceptance is one precise rounding result, rather
            # than an arbitrary tolerance that could admit modified probabilities.
            # The reconstructed distribution is normalized before quantization, so
            # float16 row sums may legitimately differ from one after storage rounding.
            reconstructed = (sums[task] / counts[:, None]).astype(np.float32).astype(probabilities.dtype)
            if not np.array_equal(probabilities, reconstructed):
                raise ValueError(f"target probabilities fail reconstruction: {task}")
            target_dtypes[task] = str(probabilities.dtype)
    return dict(validated=True, dataset=dataset, targets_sha256=sha256(targets),
                train_csv_sha256=spec["files"]["train_set.csv"], source_count=30,
                predictions_per_row=6, fold_seed=FOLD_SEED, num_folds=5,
                teacher_seeds=[42, 43, 44], sources=sources, target_dtypes=target_dtypes,
                training_target_dtype="float32", reconstruction="exact_float64_mean_to_float32_to_storage_dtype")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--dataset", choices=("neu", "vsfc"), default="neu")
    parser.add_argument("--runs", required=True, nargs="+", type=Path)
    args = parser.parse_args()
    result = validate_targets(args.targets, args.runs, args.dataset)
    out = args.targets.with_suffix(".validation.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Validated 30 teachers and six held-out predictions per row: {out}")


if __name__ == "__main__":
    main()
