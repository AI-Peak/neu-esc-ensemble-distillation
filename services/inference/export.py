"""Export the selected best state, verify reload parity, then publish an atomic pointer."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid

from .registry import (ARCHITECTURE, CRITERION, REVISION, label_schema, load_artifact,
                       profiles, run_logits, sha256, validate_artifact)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def verify_parity(original, restored, tokenizer, texts):
    """Compare logits, source order and changed padding across three batch sizes on CPU FP32."""
    import torch
    if len(texts) < 3 or len(set(texts)) < 3:
        raise ValueError("parity requires at least three distinct raw texts")
    reference, counts = run_logits(original, tokenizer, texts, batch_size=1)
    largest = 0.0
    for size in (1, 2, 8):
        actual, restored_counts = run_logits(restored, tokenizer, texts, batch_size=size)
        if counts != restored_counts:
            raise ValueError("reload tokenizer count parity failed")
        for before, after in zip(reference, actual):
            for left, right in zip(before, after):
                torch.testing.assert_close(left, right, rtol=1e-4, atol=2e-5)
                largest = max(largest, float((left - right).abs().max()))
    reverse, _ = run_logits(restored, tokenizer, list(reversed(texts)), batch_size=2)
    for before, after in zip(reference, reversed(reverse)):
        for left, right in zip(before, after):
            torch.testing.assert_close(left, right, rtol=1e-4, atol=2e-5)
    return dict(passed=True, batch_sizes=[1, 2, 8], rows=len(texts), reversed_order=True,
                device="cpu", precision="fp32", max_abs_logit_difference=largest,
                atol=2e-5, rtol=1e-4)


def export_selected(model, tokenizer, config, best, destination, texts, oof_path):
    """Only full non-fold pinned raw ViSoBERT ED runs may enter the production registry."""
    import torch
    from safetensors.torch import save_file

    if (config["backbone"] != "visobert" or config["setup"] != "mtl_ed"
            or config.get("fold") is not None or not config["benchmark_eligible"]
            or config.get("revision") != REVISION or config.get("model_path_override")
            or config["selection"] != CRITERION):
        raise ValueError("deploy export requires a full benchmark-eligible pinned raw ViSoBERT MTL-ED student")
    profile_id = "uit" if config["dataset"] == "vsfc" else config["dataset"]
    profile = profiles()[profile_id]
    oof_path = Path(oof_path)
    validation_path = oof_path.with_suffix(".validation.json")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if (validation.get("validated") is not True or validation.get("targets_sha256") != sha256(oof_path)
            or validation.get("dataset") != config["dataset"]
            or validation.get("train_csv_sha256") != config["data_files"]["train_set.csv"]
            or validation.get("source_count") != 30 or validation.get("predictions_per_row") != 6):
        raise ValueError("OOF provenance missing/mismatched: run scripts/model_oof.py first")
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    root = Path(destination) / profile_id
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    stage = versions / ("_staging_" + version)
    stage.mkdir()
    device = next(model.parameters()).device
    was_training = model.training
    try:
        model.to("cpu").float().eval()
        (stage / "encoder").mkdir()
        model.encoder.config.save_pretrained(stage / "encoder")
        tokenizer.save_pretrained(stage / "tokenizer")
        save_file({k: value.detach().cpu().contiguous() for k, value in model.state_dict().items()},
                  str(stage / "model.safetensors"))
        write_json(stage / "training_config.json", config)
        shutil.copyfile(validation_path, stage / "oof_validation.json")
        manifest = dict(format_version=1, architecture=ARCHITECTURE, profile=profile_id,
                        schema_id=profile["schema_id"], labels=label_schema(profile),
                        model_id=f"{profile_id}-visobert-mtl-ed-s{config['seed']}", model_version=version,
                        setup="mtl_ed", backbone=dict(model_id="uitnlp/visobert", revision=REVISION),
                        preprocessing=dict(kind="raw", use_fast=False, max_length=128),
                        created_at=datetime.now(timezone.utc).isoformat(),
                        provenance=dict(seed=config["seed"], best_epoch=best["epoch"],
                                        selection_score=best["score"], criterion=CRITERION,
                                        runner_sha256=config["code"]["runner_sha256"],
                                        git_commit=config["code"].get("git_commit"),
                                        benchmark_eligible=True, data_sha256=config["data_files"],
                                        environment=config.get("environment"),
                                        oof=dict(targets_sha256=sha256(oof_path),
                                                 validation_sha256=sha256(validation_path),
                                                 train_csv_sha256=validation["train_csv_sha256"],
                                                 source_count=30, predictions_per_row=6)))
        restored, restored_tokenizer = load_artifact(stage, manifest)
        # Compare tokenizer identity as well as predictions. All probe texts remain private in memory.
        if tokenizer(texts, truncation=False)["input_ids"] != restored_tokenizer(texts, truncation=False)["input_ids"]:
            raise ValueError("saved tokenizer differs from training tokenizer")
        manifest["parity"] = verify_parity(model, restored, restored_tokenizer, texts)
        write_json(stage / "parity.json", manifest["parity"])
        manifest["files"] = {p.relative_to(stage).as_posix(): sha256(p)
                             for p in stage.rglob("*") if p.is_file()}
        write_json(stage / "manifest.json", manifest)
        validate_artifact(stage, profile)
        published = versions / version
        os.replace(stage, published)
        pointer = root / ("current_" + uuid.uuid4().hex + ".tmp")
        write_json(pointer, dict(version=version))
        os.replace(pointer, root / "current.json")
        return published
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        model.to(device)
        model.train(was_training)
