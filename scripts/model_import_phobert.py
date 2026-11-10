"""Import and verify a local fine-tuned PhoBERT MTL-ED checkpoint into a versioned safetensors bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.inference.export import verify_parity, write_json
from services.inference import phobert_config
from services.inference.preprocessing import (TextPreprocessor,
                                            underthesea_spec)
from services.inference.phobert_config import (EXPECTED_PHOBERT_CONFIG,
                                              PHOBERT_CONFIG_CONTRACT,
                                              PHOBERT_MODEL_ID,
                                              verify_phobert_config_object)
from services.inference.registry import (ARCHITECTURE, CRITERION,
                                         PHOBERT_REVISION, label_schema,
                                         load_artifact, profiles, run_logits,
                                         sha256, validate_artifact)

PINNED_NEU_RAW_SHA256 = {
    "train_set.csv": "8a18a73ca21105e0b424829cc41395719be98dd7f01bf3d962eca86e7a1501ec",
    "val_set.csv": "0b2567fe5374cf9b8d22de92ce71d3f9bfa036dffac46fa6f7a5650e85c81169",
    "test_set.csv": "cdd81b2c7b96752f9f45d05e273dac521425ceff71ab312",
}

DEFAULT_RAW_PROBES = [
    "Xin chào thầy cô ạ!",
    "Cơ sở vật chất phòng học A2 rất tốt 😊👍",
    "Tiếng Việt tổ hợp: Trường đại học Kinh tế Quốc dân",
    "Câu có\nnhiều dòng\nvà   khoảng trắng.",
    "Văn_bản có sẵn dấu_gạch_dưới ở đây.",
    "ko bt hnay có học ko mn ơi???",
    "Sinh viên đăng ký tín chỉ học kỳ mới gặp lỗi hệ thống đào tạo. " * 25,
]


def _canonical_digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_local_config_dir(cfg_dir: Path, origin: str) -> tuple[object, dict]:
    from transformers import AutoConfig

    cfg_file = cfg_dir / "config.json"
    if not cfg_file.is_file():
        raise ValueError(
            f"Prepared PhoBERT encoder config not found at {cfg_file}. "
            f"Run: .\\.venv\\Scripts\\python.exe scripts\\model_prepare_phobert.py --out runtime\\cache\\phobert-base-v2"
        )
    prov_file = cfg_dir / "config_provenance.json"
    if prov_file.is_file():
        prov = json.loads(prov_file.read_text(encoding="utf-8"))
        if (prov.get("model_id") != PHOBERT_MODEL_ID
                or prov.get("revision") != PHOBERT_REVISION
                or prov.get("config_sha256") != sha256(cfg_file)):
            raise ValueError(
                f"Prepared encoder config provenance mismatch in {prov_file}; re-run scripts/model_prepare_phobert.py"
            )
    encoder_cfg = AutoConfig.from_pretrained(
        str(cfg_dir),
        local_files_only=True,
        trust_remote_code=False,
    )
    return encoder_cfg, {
        "origin": origin,
        "source_config_sha256": sha256(cfg_file),
    }


def _resolve_encoder_config(source: Path, encoder_config_dir: Path | None) -> tuple[object, dict]:
    """Load PhoBERT encoder config strictly offline without network downloads."""
    from transformers import AutoConfig

    if encoder_config_dir is not None:
        target = Path(encoder_config_dir)
        if target.is_file():
            if target.name != "config.json":
                raise ValueError(f"Encoder config file must be named config.json, got: {target}")
            encoder_cfg, meta = _load_local_config_dir(target.parent, origin="explicit_encoder_config")
        elif target.is_dir():
            encoder_cfg, meta = _load_local_config_dir(target, origin="explicit_encoder_config")
        else:
            raise ValueError(
                f"Prepared PhoBERT encoder config path does not exist: {target}. "
                f"Run: .\\.venv\\Scripts\\python.exe scripts\\model_prepare_phobert.py --out runtime\\cache\\phobert-base-v2"
            )
    elif (source / "encoder" / "config.json").is_file():
        encoder_cfg, meta = _load_local_config_dir(source / "encoder", origin="source_encoder_dir")
    else:
        try:
            encoder_cfg = AutoConfig.from_pretrained(
                PHOBERT_MODEL_ID,
                revision=PHOBERT_REVISION,
                local_files_only=True,
                trust_remote_code=False,
            )
        except Exception:
            raise ValueError(
                f"Missing local PhoBERT encoder config for {PHOBERT_MODEL_ID}@{PHOBERT_REVISION} "
                f"(neither --encoder-config, {source / 'encoder' / 'config.json'}, nor local Hugging Face cache found). "
                f"Prepare it once with: .\\.venv\\Scripts\\python.exe scripts\\model_prepare_phobert.py "
                f"--out runtime\\cache\\phobert-base-v2 --source {source} "
                f"and pass --encoder-config runtime\\cache\\phobert-base-v2"
            ) from None

        cfg_sha = None
        try:
            from huggingface_hub import try_to_load_from_cache

            cached_path = try_to_load_from_cache(
                repo_id=PHOBERT_MODEL_ID,
                filename="config.json",
                revision=PHOBERT_REVISION,
            )
            if isinstance(cached_path, str) and Path(cached_path).is_file():
                cfg_sha = sha256(cached_path)
        except Exception:
            cfg_sha = None
        if cfg_sha is None:
            cfg_sha = _canonical_digest(encoder_cfg.to_dict())
        meta = {
            "origin": "local_hf_cache",
            "source_config_sha256": cfg_sha,
        }

    # Common gate for explicit file/directory, source/encoder, and pinned HF cache.
    # Run before model construction, staging, and the already-installed shortcut.
    verify_phobert_config_object(encoder_cfg)

    meta.update({
        "semantic_contract": PHOBERT_CONFIG_CONTRACT,
        "validator_sha256": sha256(Path(phobert_config.__file__)),
        "inference_config": {field: getattr(encoder_cfg, field) for field in EXPECTED_PHOBERT_CONFIG},
        "attention_implementation": encoder_cfg._attn_implementation,
        "execution": {"device": "cpu", "dtype": "float32", "training": False},
        "model_type": encoder_cfg.model_type,
        "vocab_size": encoder_cfg.vocab_size,
        "hidden_size": encoder_cfg.hidden_size,
        "num_hidden_layers": encoder_cfg.num_hidden_layers,
        "num_attention_heads": encoder_cfg.num_attention_heads,
        "intermediate_size": encoder_cfg.intermediate_size,
        "max_position_embeddings": encoder_cfg.max_position_embeddings,
        "pad_token_id": encoder_cfg.pad_token_id,
    })
    return encoder_cfg, meta


def _offline_raw_smoke(model, tokenizer, prep_spec: dict) -> dict:
    """Verify raw Vietnamese preprocessing + inference works completely offline."""
    preprocessor = TextPreprocessor(prep_spec)
    orig_socket = socket.socket

    def _blocked_socket(*args, **kwargs):
        raise RuntimeError("Network access attempted during offline PhoBERT verification")

    socket.socket = _blocked_socket
    try:
        segmented = preprocessor.transform(DEFAULT_RAW_PROBES)
        outputs, lengths = run_logits(model, tokenizer, segmented, batch_size=4, max_length=128)
    finally:
        socket.socket = orig_socket

    if len(outputs) != len(DEFAULT_RAW_PROBES):
        raise ValueError("offline smoke output count mismatch")
    if not any(count > 128 for count in lengths):
        raise ValueError("offline smoke failed to exercise >128 token truncation")
    return {
        "passed": True,
        "offline_socket_blocked": True,
        "probe_count": len(DEFAULT_RAW_PROBES),
        "truncated_probes": sum(1 for c in lengths if c > 128),
    }


def _prepare_data_verification_inputs(source: Path, config: dict, data_dir: Path | None) -> dict | None:
    """Validate requested dataset files/hashes and historical logit file presence before import."""
    if data_dir is None:
        return None

    data_path = Path(data_dir)
    if not data_path.exists() or not data_path.is_dir():
        raise ValueError(f"Requested dataset verification directory does not exist: {data_path}")

    verified_files = {}
    expected_hashes = config["data_files"]
    for filename, expected_sha in sorted(expected_hashes.items()):
        candidate = data_path / filename
        if not candidate.is_file():
            raise ValueError(f"Dataset verification failed: missing required file {candidate}")
        actual_sha = sha256(candidate)
        if actual_sha != expected_sha:
            raise ValueError(
                f"Dataset verification failed: SHA-256 mismatch for {filename} "
                f"(expected {expected_sha}, got {actual_sha})"
            )
        verified_files[filename] = actual_sha

    val_raw_path = data_path / "val_set.csv"
    if not val_raw_path.is_file():
        raise ValueError(f"Dataset verification failed: missing raw validation file {val_raw_path}")
    raw_val_sha = sha256(val_raw_path)
    raw_expected_map = config.get("raw_data_files") or (
        PINNED_NEU_RAW_SHA256 if config.get("dataset") == "neu" else {}
    )
    if "val_set.csv" in raw_expected_map:
        expected_raw_sha = raw_expected_map["val_set.csv"]
        if raw_val_sha != expected_raw_sha:
            raise ValueError(
                f"Dataset verification failed: val_set.csv SHA-256 mismatch "
                f"(expected {expected_raw_sha}, got {raw_val_sha})"
            )
    verified_files["val_set.csv"] = raw_val_sha

    logits_npz = source / "run" / "logits.npz"
    if not logits_npz.is_file():
        raise ValueError(f"Dataset verification failed: missing historical logits archive {logits_npz}")
    logits_sha = sha256(logits_npz)

    preds_path = source / "run" / "predictions.csv"
    preds_sha = sha256(preds_path) if preds_path.is_file() else None

    return {
        "data_dir": data_path.resolve(),
        "verified_data_files": verified_files,
        "logits_npz_sha256": logits_sha,
        "predictions_csv_sha256": preds_sha,
    }


def _extract_validated_labels(frame, filename: str, expected_num_labels: dict) -> tuple[object, object]:
    import numpy as np

    missing_cols = {"text", "sentiment", "classification"} - set(frame.columns)
    if missing_cols:
        raise ValueError(f"{filename}: missing required columns {sorted(missing_cols)}")
    if len(frame) == 0:
        raise ValueError(f"{filename}: dataset split is empty")
    if frame["text"].isna().any() or any(not str(t).strip() for t in frame["text"].tolist()):
        raise ValueError(f"{filename}: contains null or blank text rows")

    out = {}
    for task, col in (("sentiment", "sentiment"), ("topic", "classification")):
        vals = frame[col].to_numpy(dtype=float)
        if not np.all(np.isfinite(vals)) or not np.all(vals == np.round(vals)):
            raise ValueError(f"{filename}: non-integer {col} labels")
        arr = vals.astype(np.int64)
        if arr.min() < 0 or arr.max() >= expected_num_labels[task]:
            raise ValueError(f"{filename}: {col} label out of range")
        out[task] = arr
    return out["sentiment"], out["topic"]


def _evaluate_optional_data(
    source: Path,
    model,
    tokenizer,
    prep_spec: dict,
    config: dict,
    data_inputs: dict | None,
    expected_num_labels: dict,
) -> dict:
    """Evaluate processed validation parity and raw adapter quality when requested."""
    if data_inputs is None:
        return {
            "status": "not_requested",
            "requested": False,
            "executed": False,
            "passed": None,
            "reason": "Optional dataset verification was not requested (--data-dir not supplied).",
            "historical_fp16_comparison": {
                "status": "not_requested",
                "executed": False,
                "passed": None,
            },
            "raw_adapter_val_comparison": {
                "status": "not_requested",
                "executed": False,
                "passed": None,
            },
        }

    import numpy as np
    import pandas as pd
    from sklearn.metrics import accuracy_score, f1_score

    data_dir = data_inputs["data_dir"]
    verified_files = data_inputs["verified_data_files"]
    val_proc_path = data_dir / "val_set_processed.csv"
    val_raw_path = data_dir / "val_set.csv"

    df_proc = pd.read_csv(val_proc_path)
    df_raw = pd.read_csv(val_raw_path)
    y_sent, y_topic = _extract_validated_labels(df_proc, "val_set_processed.csv", expected_num_labels)
    raw_y_sent, raw_y_topic = _extract_validated_labels(df_raw, "val_set.csv", expected_num_labels)
    if len(df_raw) != len(df_proc) or not np.array_equal(raw_y_sent, y_sent) or not np.array_equal(raw_y_topic, y_topic):
        raise ValueError("Dataset verification failed: val_set.csv is not row/label aligned with val_set_processed.csv")

    n_rows = len(df_proc)
    raw_prefix = verified_files["val_set.csv"][:12]
    expected_ids = [f"validation:{row:06d}:{raw_prefix}" for row in range(n_rows)]

    logits_npz = source / "run" / "logits.npz"
    npz = np.load(logits_npz)
    required_npz_keys = {"val_ids", "val_sentiment", "val_topic", "val_labels_sentiment", "val_labels_topic"}
    missing_npz_keys = required_npz_keys - set(npz.files)
    if missing_npz_keys:
        raise ValueError(f"Dataset verification failed: logits.npz missing keys {sorted(missing_npz_keys)}")

    s_hist = np.asarray(npz["val_sentiment"])
    t_hist = np.asarray(npz["val_topic"])
    if s_hist.shape != (n_rows, expected_num_labels["sentiment"]) or not np.isfinite(s_hist).all():
        raise ValueError(
            f"Dataset verification failed: logits.npz val_sentiment shape/finiteness mismatch "
            f"(got {s_hist.shape}, expected {(n_rows, expected_num_labels['sentiment'])})"
        )
    if t_hist.shape != (n_rows, expected_num_labels["topic"]) or not np.isfinite(t_hist).all():
        raise ValueError(
            f"Dataset verification failed: logits.npz val_topic shape/finiteness mismatch "
            f"(got {t_hist.shape}, expected {(n_rows, expected_num_labels['topic'])})"
        )

    actual_ids = [str(x) for x in npz["val_ids"].tolist()]
    if actual_ids != expected_ids:
        raise ValueError("Dataset verification failed: logits.npz val_ids do not match expected row order or val_set.csv prefix")

    npz_y_sent = np.asarray(npz["val_labels_sentiment"], dtype=np.int64)
    npz_y_topic = np.asarray(npz["val_labels_topic"], dtype=np.int64)
    if npz_y_sent.shape != (n_rows,) or not np.array_equal(npz_y_sent, y_sent):
        raise ValueError("Dataset verification failed: logits.npz val_labels_sentiment does not match val_set_processed.csv")
    if npz_y_topic.shape != (n_rows,) or not np.array_equal(npz_y_topic, y_topic):
        raise ValueError("Dataset verification failed: logits.npz val_labels_topic does not match val_set_processed.csv")

    preds_path = source / "run" / "predictions.csv"
    if preds_path.is_file():
        df_preds = pd.read_csv(preds_path)
        missing_pred_cols = {"split", "sample_id", "sentiment_true", "topic_true"} - set(df_preds.columns)
        if missing_pred_cols:
            raise ValueError(
                f"Dataset verification failed: predictions.csv missing required columns {sorted(missing_pred_cols)}"
            )
        df_preds_val = df_preds[df_preds["split"] == "val"]
        if (df_preds_val["sample_id"].astype(str).tolist() != expected_ids
                or not np.array_equal(df_preds_val["sentiment_true"].to_numpy(np.int64), y_sent)
                or not np.array_equal(df_preds_val["topic_true"].to_numpy(np.int64), y_topic)):
            raise ValueError("Dataset verification failed: predictions.csv validation rows do not align with dataset IDs/labels")

    proc_texts = df_proc["text"].astype(str).tolist()
    proc_logits, _ = run_logits(model, tokenizer, proc_texts, batch_size=64, max_length=128)
    s_proc = np.stack([row[0].numpy() for row in proc_logits], axis=0)
    t_proc = np.stack([row[1].numpy() for row in proc_logits], axis=0)

    s_diff = np.abs(s_proc - s_hist)
    t_diff = np.abs(t_proc - t_hist)
    s_agree = float((s_proc.argmax(-1) == s_hist.argmax(-1)).mean())
    t_agree = float((t_proc.argmax(-1) == t_hist.argmax(-1)).mean())
    if s_agree < 0.99 or t_agree < 0.99 or float(s_diff.max()) >= 0.25 or float(t_diff.max()) >= 0.25:
        raise ValueError(
            f"Dataset verification failed: processed validation mismatch vs historical logits "
            f"(agreement={s_agree:.4f}/{t_agree:.4f}, max_diff={float(s_diff.max()):.4f}/{float(t_diff.max()):.4f})"
        )

    preprocessor = TextPreprocessor(prep_spec)
    raw_texts = df_raw["text"].astype(str).tolist()
    seg_texts = preprocessor.transform(raw_texts)
    seg_logits, _ = run_logits(model, tokenizer, seg_texts, batch_size=64, max_length=128)
    s_seg = np.stack([row[0].numpy() for row in seg_logits], axis=0)
    t_seg = np.stack([row[1].numpy() for row in seg_logits], axis=0)

    return {
        "status": "passed",
        "requested": True,
        "executed": True,
        "passed": True,
        "verified_data_files": verified_files,
        "split": "val",
        "rows": int(n_rows),
        "processed_cpu_fp32": {
            "sentiment_accuracy": float(accuracy_score(y_sent, s_proc.argmax(-1))),
            "sentiment_macro_f1": float(f1_score(y_sent, s_proc.argmax(-1), average="macro")),
            "topic_accuracy": float(accuracy_score(y_topic, t_proc.argmax(-1))),
            "topic_macro_f1": float(f1_score(y_topic, t_proc.argmax(-1), average="macro")),
        },
        "historical_fp16_comparison": {
            "status": "passed",
            "executed": True,
            "passed": True,
            "logits_npz_sha256": data_inputs["logits_npz_sha256"],
            "sentiment_max_abs_diff": float(s_diff.max()),
            "sentiment_mean_abs_diff": float(s_diff.mean()),
            "sentiment_pred_agreement": s_agree,
            "topic_max_abs_diff": float(t_diff.max()),
            "topic_mean_abs_diff": float(t_diff.mean()),
            "topic_pred_agreement": t_agree,
        },
        "raw_adapter_val_comparison": {
            "status": "passed",
            "executed": True,
            "passed": True,
            "raw_csv_sha256": verified_files["val_set.csv"],
            "exact_text_match_rate": float(sum(a == b for a, b in zip(seg_texts, proc_texts)) / len(proc_texts)),
            "sentiment_agreement_vs_processed": float((s_seg.argmax(-1) == s_proc.argmax(-1)).mean()),
            "sentiment_accuracy": float(accuracy_score(y_sent, s_seg.argmax(-1))),
            "sentiment_macro_f1": float(f1_score(y_sent, s_seg.argmax(-1), average="macro")),
            "topic_agreement_vs_processed": float((t_seg.argmax(-1) == t_proc.argmax(-1)).mean()),
            "topic_accuracy": float(accuracy_score(y_topic, t_seg.argmax(-1))),
            "topic_macro_f1": float(f1_score(y_topic, t_seg.argmax(-1), average="macro")),
        },
    }


def _write_optional_report(report_out: Path | None, payload: dict) -> None:
    if report_out is None:
        return
    target = Path(report_out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f"{target.name}.{uuid.uuid4().hex[:8]}.tmp"
    write_json(tmp, payload)
    os.replace(tmp, target)


def import_phobert_checkpoint(
    source: Path,
    model_root: Path,
    profile_id: str = "neu",
    data_dir: Path | None = None,
    encoder_config_dir: Path | None = None,
    verify_only: bool = False,
    stage_only: bool = False,
    report_out: Path | None = None,
) -> dict:
    import math
    import torch
    from safetensors.torch import save_file
    from transformers import AutoTokenizer
    from services.inference.architecture import build_model

    if profile_id != "neu":
        raise ValueError("PhoBERT checkpoint import currently supports only profile 'neu'")
    profile = profiles()[profile_id]
    expected_dataset = "neu"

    source = Path(source).resolve()
    checkpoint_path = source / "model.pt"
    model_info_path = source / "model_info.json"
    config_path = source / "run" / "config.json"
    metrics_path = source / "run" / "metrics.json"
    tokenizer_dir = source / "tokenizer"

    for required_path in (checkpoint_path, model_info_path, config_path, metrics_path):
        if not required_path.is_file():
            raise ValueError(f"missing required source file: {required_path}")
    if not tokenizer_dir.is_dir():
        raise ValueError(f"missing required source tokenizer directory: {tokenizer_dir}")

    checkpoint_sha = sha256(checkpoint_path)
    importer_sha = sha256(Path(__file__).resolve())
    model_info = json.loads(model_info_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    expected_num_labels = {"sentiment": len(profile["sentiment"]), "topic": len(profile["topic"])}
    if (model_info.get("backbone") != "phobert"
            or model_info.get("setup") != "mtl_ed"
            or model_info.get("model_id") != PHOBERT_MODEL_ID
            or model_info.get("revision") != PHOBERT_REVISION
            or model_info.get("max_length") != 128
            or type(model_info.get("seed")) is not int
            or type(model_info.get("best_epoch")) is not int
            or model_info["best_epoch"] < 1
            or model_info.get("num_labels") != expected_num_labels):
        raise ValueError("source model_info.json failed validation")

    seed = model_info["seed"]
    best_epoch = model_info["best_epoch"]
    runner_sha = config.get("code", {}).get("runner_sha256")
    data_files = config.get("data_files", {})
    if (config.get("dataset") != expected_dataset
            or config.get("backbone") != "phobert"
            or config.get("setup") != "mtl_ed"
            or config.get("fold") is not None
            or config.get("model_path_override")
            or config.get("model_id") != PHOBERT_MODEL_ID
            or config.get("revision") != PHOBERT_REVISION
            or config.get("seed") != seed
            or config.get("benchmark_eligible") is not True
            or config.get("selection") != CRITERION
            or not isinstance(runner_sha, str) or len(runner_sha) != 64
            or set(data_files) != {"train_set_processed.csv", "val_set_processed.csv", "test_set_processed.csv"}):
        raise ValueError("source run/config.json failed validation")

    selection_score = metrics.get("selection_score")
    if (metrics.get("status") != "COMPLETED"
            or metrics.get("benchmark_eligible") is not True
            or metrics.get("best_epoch") != best_epoch
            or metrics.get("runner_sha256") != runner_sha
            or not isinstance(selection_score, (int, float))
            or not math.isfinite(selection_score)):
        raise ValueError("source run/metrics.json failed validation")

    teacher_cfg = config.get("ensemble_teacher", {})
    teacher_sources = teacher_cfg.get("sources", [])
    if len(teacher_sources) != 30:
        raise ValueError("expected 30 reported ensemble teacher sources in run/config.json")

    data_inputs = _prepare_data_verification_inputs(source, config, data_dir)

    prep_spec = underthesea_spec()
    encoder_cfg, encoder_meta = _resolve_encoder_config(source, encoder_config_dir)

    tokenizer = AutoTokenizer.from_pretrained(
        str(tokenizer_dir),
        use_fast=False,
        local_files_only=True,
        trust_remote_code=False,
    )
    if (tokenizer.pad_token_id is None
            or tokenizer.pad_token_id != encoder_cfg.pad_token_id
            or len(tokenizer) != encoder_cfg.vocab_size):
        raise ValueError("source tokenizer incompatible with PhoBERT encoder config")

    source_tok_hashes = {
        p.relative_to(tokenizer_dir).as_posix(): sha256(p)
        for p in sorted(tokenizer_dir.rglob("*"))
        if p.is_file()
    }
    pipeline_digest = _canonical_digest({
        "checkpoint_sha256": checkpoint_sha,
        "tokenizer_hashes": source_tok_hashes,
        "encoder_config": encoder_cfg.to_dict(),
        "preprocessing": prep_spec,
        "model_info": model_info,
        "training_config": config,
        "source_metrics": metrics,
        "importer_sha256": importer_sha,
        "encoder_config_contract_sha256": encoder_meta["validator_sha256"],
    })
    if data_inputs is None:
        version_digest = pipeline_digest
    else:
        version_digest = _canonical_digest({
            "pipeline_digest": pipeline_digest,
            "verified_data_files": data_inputs["verified_data_files"],
            "logits_npz_sha256": data_inputs["logits_npz_sha256"],
            "predictions_csv_sha256": data_inputs["predictions_csv_sha256"],
        })

    model_id = f"{profile_id}-phobert-mtl-ed-s{seed}"
    model_version = f"{model_id}-e{best_epoch}-{version_digest[:12]}"

    root = Path(model_root).resolve() / profile_id
    versions = root / "versions"
    published = versions / model_version
    if not verify_only and published.exists():
        existing_manifest = validate_artifact(published, profile)
        existing_dv = existing_manifest.get("verification", {}).get("dataset_verification", {})
        can_reuse = False
        if data_inputs is None:
            can_reuse = existing_dv.get("status") == "not_requested"
        else:
            can_reuse = (
                existing_dv.get("status") == "passed"
                and existing_dv.get("executed") is True
                and existing_dv.get("passed") is True
                and existing_dv.get("verified_data_files") == data_inputs["verified_data_files"]
                and existing_dv.get("historical_fp16_comparison", {}).get("logits_npz_sha256") == data_inputs["logits_npz_sha256"]
            )
        if can_reuse:
            if not stage_only:
                pointer = root / f"current_{uuid.uuid4().hex}.tmp"
                write_json(pointer, {"version": model_version})
                os.replace(pointer, root / "current.json")
            report = {
                "status": "already_installed",
                "profile": profile_id,
                "model_id": model_id,
                "model_version": model_version,
                "bundle_path": str(published),
                "activated": not stage_only,
                "original_checkpoint_sha256": checkpoint_sha,
                "parity": existing_manifest["parity"],
                "verification": existing_manifest["verification"],
            }
            _write_optional_report(report_out, report)
            return report

    model = build_model(encoder_cfg, expected_num_labels)
    raw_state = torch.load(str(checkpoint_path), map_location="cpu", weights_only=True)
    if not isinstance(raw_state, dict):
        raise ValueError("checkpoint did not deserialize to a state dict")
    expected_state = model.state_dict()
    if set(raw_state) != set(expected_state):
        raise ValueError("checkpoint tensor keys do not match architecture")
    for key, expected_tensor in expected_state.items():
        tensor = raw_state[key]
        if not isinstance(tensor, torch.Tensor) or tensor.shape != expected_tensor.shape:
            raise ValueError(f"checkpoint tensor shape mismatch at {key}")
        if not torch.isfinite(tensor).all():
            raise ValueError(f"checkpoint tensor contains NaN or Inf at {key}")
    model.load_state_dict(raw_state, strict=True)
    model.to("cpu").float().eval()

    temp_ctx = None
    if verify_only:
        temp_ctx = tempfile.TemporaryDirectory(prefix="phobert-verify-")
        stage = Path(temp_ctx.name) / "stage"
        stage.mkdir(parents=True)
    else:
        versions.mkdir(parents=True, exist_ok=True)
        stage = versions / f"_staging_{model_version}_{uuid.uuid4().hex[:8]}"
        stage.mkdir()

    try:
        (stage / "encoder").mkdir()
        encoder_cfg.save_pretrained(stage / "encoder")
        saved_encoder_sha = sha256(stage / "encoder" / "config.json")
        tokenizer.save_pretrained(stage / "tokenizer")
        save_file(
            {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
            str(stage / "model.safetensors"),
        )
        write_json(stage / "preprocessing.json", prep_spec)
        write_json(stage / "training_config.json", config)
        write_json(stage / "source_model_info.json", model_info)
        write_json(stage / "source_metrics.json", metrics)

        manifest = {
            "format_version": 2,
            "architecture": ARCHITECTURE,
            "profile": profile_id,
            "schema_id": profile["schema_id"],
            "labels": label_schema(profile),
            "model_id": model_id,
            "model_version": model_version,
            "setup": "mtl_ed",
            "backbone": {
                "model_id": PHOBERT_MODEL_ID,
                "revision": PHOBERT_REVISION,
            },
            "preprocessing": prep_spec,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "seed": seed,
                "best_epoch": best_epoch,
                "selection_score": float(selection_score),
                "criterion": CRITERION,
                "pipeline_digest": pipeline_digest,
                "original_checkpoint_sha256": checkpoint_sha,
                "runner_sha256": runner_sha,
                "importer_sha256": importer_sha,
                "encoder_config": {
                    **encoder_meta,
                    "saved_config_sha256": saved_encoder_sha,
                },
                "benchmark_eligible": True,
                "data_sha256": data_files,
                "training_environment": config.get("environment"),
                "oof": {
                    "status": "reported",
                    "audited": False,
                    "note": "Reported in run/config.json; 30 teacher checkpoints and OOF target archive are not bundled locally.",
                    "targets_path_reported": teacher_cfg.get("targets"),
                    "gamma": teacher_cfg.get("gamma"),
                    "source_count": len(teacher_sources),
                    "predictions_per_row": 6,
                    "sources": teacher_sources,
                },
            },
        }

        restored, restored_tokenizer = load_artifact(stage, manifest)
        probe_segmented = TextPreprocessor(prep_spec).transform(DEFAULT_RAW_PROBES)
        if tokenizer(probe_segmented, truncation=False)["input_ids"] != restored_tokenizer(probe_segmented, truncation=False)["input_ids"]:
            raise ValueError("saved PhoBERT tokenizer differs from source tokenizer")

        parity = verify_parity(model, restored, restored_tokenizer, probe_segmented)
        smoke = _offline_raw_smoke(restored, restored_tokenizer, prep_spec)
        data_eval = _evaluate_optional_data(
            source,
            restored,
            restored_tokenizer,
            prep_spec,
            config,
            data_inputs,
            expected_num_labels,
        )
        verification = {
            "passed": True,
            "inference_ready": True,
            "structural_checks": {
                "passed": True,
                "strict_state_dict_keys": len(expected_state),
                "all_weights_finite": True,
                "tokenizer_roundtrip_matched": True,
                "encoder_config_sha256": saved_encoder_sha,
            },
            "reload_parity": {
                "passed": parity["passed"],
                "max_abs_logit_difference": parity["max_abs_logit_difference"],
                "batch_sizes": parity["batch_sizes"],
                "reversed_order": parity["reversed_order"],
            },
            "strict_state_dict_keys": len(expected_state),
            "all_weights_finite": True,
            "tokenizer_roundtrip_matched": True,
            "offline_raw_smoke": smoke,
            "dataset_verification": data_eval,
        }
        manifest["parity"] = parity
        manifest["verification"] = verification
        write_json(stage / "parity.json", parity)
        write_json(stage / "verification.json", verification)
        manifest["files"] = {
            p.relative_to(stage).as_posix(): sha256(p)
            for p in stage.rglob("*")
            if p.is_file()
        }
        write_json(stage / "manifest.json", manifest)
        validate_artifact(stage, profile)

        if verify_only:
            report = {
                "status": "verified_only",
                "profile": profile_id,
                "model_id": model_id,
                "model_version": model_version,
                "activated": False,
                "original_checkpoint_sha256": checkpoint_sha,
                "parity": parity,
                "verification": verification,
            }
            _write_optional_report(report_out, report)
            return report

        os.replace(stage, published)
        if not stage_only:
            pointer = root / f"current_{uuid.uuid4().hex}.tmp"
            write_json(pointer, {"version": model_version})
            os.replace(pointer, root / "current.json")

        report = {
            "status": "staged" if stage_only else "imported_and_activated",
            "profile": profile_id,
            "model_id": model_id,
            "model_version": model_version,
            "bundle_path": str(published),
            "activated": not stage_only,
            "original_checkpoint_sha256": checkpoint_sha,
            "parity": parity,
            "verification": verification,
        }
        _write_optional_report(report_out, report)
        return report
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("demo"), help="Directory containing model.pt, model_info.json, tokenizer/, run/")
    parser.add_argument("--model-root", type=Path, default=Path("runtime/models"))
    parser.add_argument("--profile", choices=("neu",), default="neu")
    parser.add_argument(
        "--encoder-config",
        type=Path,
        default=None,
        help="Directory containing prepared PhoBERT config.json (defaults to runtime/cache/phobert-base-v2 if present)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Optional pinned NEU dataset directory to verify processed/raw splits before publishing",
    )
    parser.add_argument("--verify-only", action="store_true", help="Verify checkpoint and parity without writing to model-root")
    parser.add_argument("--stage-only", action="store_true", help="Write and verify versioned bundle without updating current.json")
    parser.add_argument("--report-out", type=Path, default=None, help="Optional JSON path to write verification/import report")
    args = parser.parse_args()

    encoder_config_dir = args.encoder_config
    if encoder_config_dir is None and not (args.source / "encoder" / "config.json").is_file():
        default_prepared = Path("runtime/cache/phobert-base-v2")
        if (default_prepared / "config.json").is_file():
            encoder_config_dir = default_prepared

    try:
        report = import_phobert_checkpoint(
            source=args.source,
            model_root=args.model_root,
            profile_id=args.profile,
            data_dir=args.data_dir,
            encoder_config_dir=encoder_config_dir,
            verify_only=args.verify_only,
            stage_only=args.stage_only,
            report_out=args.report_out,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
