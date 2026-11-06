"""Tiny synthetic folds verify OOF auditing without training any teachers."""
import json

import numpy as np
import pytest

from scripts.model_oof import validate_targets
from services.inference.registry import sha256
from src_improvement import neu_esc_improvement as runner


@pytest.fixture
def oof(tmp_path, monkeypatch):
    files = {f"{s}_set{p}.csv": str(i) * 64 for i, s in enumerate(("train", "val", "test"), 1)
             for p in ("", "_processed")}
    spec = dict(files=files, split_sizes=dict(train=10), num_labels=dict(sentiment=4, topic=10))
    monkeypatch.setitem(runner.DATASETS, "neu", spec)
    runs = []
    rng = np.random.RandomState(9)
    sums = {t: np.zeros((10, n)) for t, n in spec["num_labels"].items()}
    for backbone in ("phobert", "visobert"):
        for seed in (42, 43, 44):
            for fold in range(5):
                run = tmp_path / f"{backbone}-mtl-s{seed}-f{fold}of5"
                run.mkdir()
                runs.append(run)
                rows = runner.fold_rows(10, fold, 5)
                processed = "_processed" if backbone == "phobert" else ""
                config = dict(backbone=backbone, seed=seed, dataset="neu", setup="mtl",
                              revision=runner.BACKBONES[backbone]["revision"],
                              benchmark_eligible=True, tasks=["sentiment", "topic"], epochs=20,
                              selection="mean val macro-F1 over both tasks",
                              data_files={f"{s}_set{processed}.csv": files[f"{s}_set{processed}.csv"]
                                          for s in ("train", "val", "test")},
                              fold=dict(fold=fold, num_folds=5, fold_seed=runner.FOLD_SEED, held_out_rows=len(rows)),
                              code=dict(runner_sha256="a" * 64))
                (run / "config.json").write_text(json.dumps(config))
                (run / "metrics.json").write_text(json.dumps(dict(status="COMPLETED", benchmark_eligible=True,
                                                                    best_epoch=2, runner_sha256="a" * 64)))
                logits = {t: rng.randn(len(rows), n) for t, n in spec["num_labels"].items()}
                for task in logits:
                    probabilities = np.exp(logits[task] - logits[task].max(1, keepdims=True))
                    sums[task][rows] += probabilities / probabilities.sum(1, keepdims=True)
                np.savez_compressed(run / "oof.npz", rows=rows,
                                    train_csv_sha256=files[f"train_set{processed}.csv"],
                                    **{f"oof_{t}": v for t, v in logits.items()})
    target = tmp_path / "targets.npz"
    np.savez_compressed(target, train_csv_sha256=files["train_set.csv"], sources=[x.name for x in runs],
                        counts=np.full(10, 6), **{t: (v / 6).astype(np.float32) for t, v in sums.items()})
    return target, runs


def test_validates_six_held_out_predictions_and_hashes(oof):
    target, runs = oof
    result = validate_targets(target, runs, "neu")
    assert result["validated"] and result["source_count"] == 30
    assert result["targets_sha256"] == sha256(target)
    assert len(result["sources"]) == 30
    assert all(set(x["hashes"]) == {"config.json", "metrics.json", "oof.npz"} for x in result["sources"])


def _rewrite_targets(target, **updates):
    with np.load(target, allow_pickle=False) as arrays:
        values = dict(arrays)
    values.update(updates)
    np.savez_compressed(target, **values)


@pytest.mark.parametrize("reverse_run_arguments", [False, True])
def test_recovers_historical_float16_targets(oof, reverse_run_arguments):
    target, runs = oof
    with np.load(target) as arrays:
        tasks = {t: arrays[t].astype(np.float16) for t in ("sentiment", "topic")}
    _rewrite_targets(target, **tasks)
    result = validate_targets(target, list(reversed(runs)) if reverse_run_arguments else runs, "neu")
    assert result["validated"] and result["predictions_per_row"] == 6
    assert result["target_dtypes"] == dict(sentiment="float16", topic="float16")
    assert result["training_target_dtype"] == "float32"
    assert [source["run_name"] for source in result["sources"]] == [run.name for run in runs]


def test_float32_reconstruction_uses_archived_source_order(oof):
    target, runs = oof
    # These six softmax distributions straddle a float32 rounding midpoint:
    # reversing float64 addition changes the stored result by one float32 ULP.
    pairs = [[-.3551313890766427, -1.20758372495743],
             [-.9008775599862208, -.5212346552255718],
             [-.25416197502547827, -1.4941743569908899],
             [-.4562050836486575, -1.0042585631355792],
             [-2.2742302565768138, -.10856126163013445],
             [-.9162898527575685, -.5108262098441445]]
    probabilities = []
    for run in runs:
        path = run / "oof.npz"
        with np.load(path) as arrays:
            values = dict(arrays)
        indices = np.flatnonzero(values["rows"] == 0)
        if not len(indices):
            continue
        logits = np.array([*pairs[len(probabilities)], -1000., -1000.])
        values["oof_sentiment"][indices[0]] = logits
        exp = np.exp(logits - logits.max())
        probabilities.append(exp / exp.sum())
        np.savez_compressed(path, **values)
    forward = sum(probabilities) / 6
    backward = sum(reversed(probabilities)) / 6
    assert not np.array_equal(forward.astype(np.float32), backward.astype(np.float32))
    with np.load(target) as arrays:
        sentiment = arrays["sentiment"].copy()
    sentiment[0] = forward.astype(np.float32)
    _rewrite_targets(target, sentiment=sentiment)
    assert validate_targets(target, list(reversed(runs)), "neu")["validated"]


def test_rejects_float16_tampering_beyond_rounding_even_when_normalized(oof):
    target, runs = oof
    with np.load(target) as arrays:
        tasks = {t: arrays[t].astype(np.float16) for t in ("sentiment", "topic")}
    probabilities = tasks["sentiment"]
    probabilities[0, 0] += np.float16(.002)
    probabilities[0, 1] -= np.float16(.002)
    assert abs(float(probabilities[0].astype(np.float64).sum()) - 1) < .001
    _rewrite_targets(target, **tasks)
    with pytest.raises(ValueError, match="reconstruction"):
        validate_targets(target, runs, "neu")


@pytest.mark.parametrize("dtype", [np.float16, np.float32])
@pytest.mark.parametrize("damage", ["missing", "duplicate", "test_selection", "wrong_fold", "bad_targets", "bad_hash", "wrong_rows", "wrong_counts", "nan", "range"])
def test_rejects_damaged_or_unproven_teachers(oof, damage, dtype):
    target, runs = oof
    with np.load(target) as arrays:
        tasks = {t: arrays[t].astype(dtype) for t in ("sentiment", "topic")}
    _rewrite_targets(target, **tasks)
    if damage == "missing":
        runs = runs[:-1]
    elif damage == "duplicate":
        runs[-1] = runs[0]
    elif damage in ("test_selection", "wrong_fold"):
        path = runs[0] / "config.json"
        config = json.loads(path.read_text())
        if damage == "test_selection":
            config["selection"] = "test accuracy"
        else:
            config["fold"]["fold_seed"] = 42
        path.write_text(json.dumps(config))
    elif damage == "wrong_rows":
        path = runs[0] / "oof.npz"
        with np.load(path) as arrays:
            values = dict(arrays)
        values["rows"] = values["rows"][::-1]
        np.savez_compressed(path, **values)
    else:
        with np.load(target) as arrays:
            values = dict(arrays)
        if damage == "bad_targets":
            values["sentiment"][0] = [.25, .25, .25, .25]
        elif damage == "wrong_counts":
            values["counts"][0] = 5
        elif damage == "nan":
            values["sentiment"][0, 0] = np.nan
        elif damage == "range":
            values["topic"][0, 0] = 1.1
        else:
            values["train_csv_sha256"] = "b" * 64
        np.savez_compressed(target, **values)
    with pytest.raises(ValueError):
        validate_targets(target, runs, "neu")
