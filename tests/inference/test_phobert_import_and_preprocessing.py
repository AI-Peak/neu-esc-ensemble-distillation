"""Tests for PhoBERT Format 2 import, underthesea preprocessing, and real-checkpoint acceptance."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import unicodedata

import httpx
import pytest

import scripts.model_import_phobert as importer_mod
from scripts.model_import_phobert import import_phobert_checkpoint
from services.inference.registry import (CRITERION, PHOBERT_REVISION,
                                         ModelRegistry, ModelUnavailable,
                                         sha256)


def _allow_synthetic_config(monkeypatch):
    """Test-only seam for generic import mechanics; never used by contract tests."""
    import services.inference.registry as registry_mod

    def verify_tiny_config(cfg):
        if cfg.model_type != "roberta":
            raise ValueError("synthetic config must have model_type='roberta'")
        if cfg.max_position_embeddings < 130:
            raise ValueError("synthetic config must support max_length=128")

    monkeypatch.setattr(importer_mod, "verify_phobert_config_object", verify_tiny_config)
    monkeypatch.setattr(registry_mod, "verify_phobert_config_object", verify_tiny_config)


def _create_synthetic_phobert_source(
    root: Path,
    monkeypatch=None,
    *,
    write_encoder_dir: bool = False,
    patch_autoconfig: bool = True,
) -> tuple[Path, object]:
    """Create a tiny random Roberta/PhoBERT source checkpoint for offline mechanics tests."""
    import torch
    import transformers
    from transformers import BertTokenizer, RobertaConfig
    from services.inference.architecture import build_model

    if monkeypatch is not None:
        _allow_synthetic_config(monkeypatch)
    torch.set_num_threads(1)
    torch.manual_seed(42)
    source = root / "phobert_source"
    (source / "tokenizer").mkdir(parents=True, exist_ok=True)
    (source / "run").mkdir(parents=True, exist_ok=True)

    vocab = [
        "<pad>", "<s>", "</s>", "<unk>", "<mask>",
        "sinh_viên", "trường", "đại_học", "cơ_sở", "vật_chất",
        "rất", "tốt", "giảng_viên", "học_tập", "dịch_vụ",
    ]
    (source / "tokenizer" / "vocab.txt").write_text("\n".join(vocab), encoding="utf-8")
    tokenizer = BertTokenizer(
        str(source / "tokenizer" / "vocab.txt"),
        do_lower_case=False,
        pad_token="<pad>",
        unk_token="<unk>",
        cls_token="<s>",
        sep_token="</s>",
        mask_token="<mask>",
    )
    tokenizer.save_pretrained(source / "tokenizer")

    cfg = RobertaConfig(
        vocab_size=len(tokenizer),
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=16,
        max_position_embeddings=258,
        pad_token_id=tokenizer.pad_token_id,
        hidden_dropout_prob=0.0,
        attention_probs_dropout_prob=0.0,
    )
    model = build_model(cfg, {"sentiment": 4, "topic": 10}).eval()
    torch.save(model.state_dict(), source / "model.pt")

    if write_encoder_dir:
        (source / "encoder").mkdir(parents=True, exist_ok=True)
        cfg.save_pretrained(source / "encoder")

    if patch_autoconfig and monkeypatch is not None:
        monkeypatch.setattr(
            transformers.AutoConfig,
            "from_pretrained",
            staticmethod(lambda *args, **kwargs: cfg),
        )

    model_info = {
        "run_name": "phobert-mtl_ed-s42",
        "backbone": "phobert",
        "setup": "mtl_ed",
        "seed": 42,
        "model_id": "vinai/phobert-base-v2",
        "revision": PHOBERT_REVISION,
        "best_epoch": 10,
        "max_length": 128,
        "num_labels": {"sentiment": 4, "topic": 10},
    }
    (source / "model_info.json").write_text(json.dumps(model_info, indent=2), encoding="utf-8")

    config = {
        "run_name": "phobert-mtl_ed-s42",
        "dataset": "neu",
        "backbone": "phobert",
        "setup": "mtl_ed",
        "seed": 42,
        "code": {"runner_sha256": "b" * 64, "git_commit": None, "git_dirty": None},
        "model_id": "vinai/phobert-base-v2",
        "revision": PHOBERT_REVISION,
        "model_path_override": None,
        "data_files": {
            "train_set_processed.csv": "1" * 64,
            "val_set_processed.csv": "2" * 64,
            "test_set_processed.csv": "3" * 64,
        },
        "max_length": 128,
        "selection": CRITERION,
        "benchmark_eligible": True,
        "fold": None,
        "ensemble_teacher": {
            "targets": "/tmp/ens_targets.npz",
            "gamma": 1.0,
            "sources": [f"teacher-{i}" for i in range(30)],
        },
    }
    (source / "run" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    metrics = {
        "status": "COMPLETED",
        "run_name": "phobert-mtl_ed-s42",
        "benchmark_eligible": True,
        "runner_sha256": "b" * 64,
        "best_epoch": 10,
        "epochs_run": 20,
        "selection_score": 0.712286952,
    }
    (source / "run" / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return source, cfg


def _create_synthetic_dataset_and_logits(root: Path, source: Path, cfg) -> Path:
    """Create aligned processed/raw CSV splits and matching historical logits.npz for source."""
    import numpy as np
    import torch
    from transformers import AutoTokenizer
    from services.inference.architecture import build_model
    from services.inference.registry import run_logits

    data_dir = root / "pinned_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = [
        ("Giảng viên giảng bài rất dễ hiểu", 1, 2),
        ("Cơ sở vật chất phòng học chưa tốt", 2, 4),
        ("Thông báo lịch học kỳ mới", 0, 1),
        ("Dịch vụ hỗ trợ sinh viên nhiệt tình", 1, 4),
    ]
    proc_rows = [
        ("Giảng_viên giảng bài rất dễ hiểu", 1, 2),
        ("Cơ_sở vật_chất phòng học chưa tốt", 2, 4),
        ("Thông_báo lịch học_kỳ mới", 0, 1),
        ("Dịch_vụ hỗ_trợ sinh_viên nhiệt_tình", 1, 4),
    ]

    def _write_csv(path: Path, rows: list[tuple[str, int, int]]) -> str:
        buf = io.StringIO(newline="")
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["text", "sentiment", "classification"])
        for text, sent, topic in rows:
            writer.writerow([text, sent, topic])
        path.write_bytes(buf.getvalue().encode("utf-8"))
        return sha256(path)

    train_proc_sha = _write_csv(data_dir / "train_set_processed.csv", proc_rows[:2])
    val_proc_sha = _write_csv(data_dir / "val_set_processed.csv", proc_rows)
    test_proc_sha = _write_csv(data_dir / "test_set_processed.csv", proc_rows[1:])
    val_raw_sha = _write_csv(data_dir / "val_set.csv", raw_rows)

    config_path = source / "run" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["data_files"] = {
        "train_set_processed.csv": train_proc_sha,
        "val_set_processed.csv": val_proc_sha,
        "test_set_processed.csv": test_proc_sha,
    }
    config["raw_data_files"] = {
        "val_set.csv": val_raw_sha,
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    model = build_model(cfg, {"sentiment": 4, "topic": 10})
    state = torch.load(source / "model.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(str(source / "tokenizer"), use_fast=False, local_files_only=True)
    outputs, _ = run_logits(model, tokenizer, [r[0] for r in proc_rows], batch_size=4, max_length=128)
    s_hist = np.stack([row[0].numpy() for row in outputs], axis=0)
    t_hist = np.stack([row[1].numpy() for row in outputs], axis=0)
    y_sent = np.array([r[1] for r in proc_rows], dtype=np.int64)
    y_topic = np.array([r[2] for r in proc_rows], dtype=np.int64)
    val_ids = np.array([f"validation:{i:06d}:{val_raw_sha[:12]}" for i in range(len(proc_rows))])

    np.savez_compressed(
        source / "run" / "logits.npz",
        val_ids=val_ids,
        val_sentiment=s_hist,
        val_topic=t_hist,
        val_labels_sentiment=y_sent,
        val_labels_topic=y_topic,
    )
    with (source / "run" / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "split", "sentiment_true", "sentiment_pred", "topic_true", "topic_pred"])
        for row_idx, sid in enumerate(val_ids):
            writer.writerow([
                sid,
                "val",
                int(y_sent[row_idx]),
                int(s_hist[row_idx].argmax()),
                int(y_topic[row_idx]),
                int(t_hist[row_idx].argmax()),
            ])
    return data_dir


def test_phobert_import_status_offline_and_idempotency(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")

    source, _ = _create_synthetic_phobert_source(tmp_path, monkeypatch)
    model_root = tmp_path / "models"

    first = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")
    assert first["status"] == "imported_and_activated"
    assert first["activated"] is True
    assert first["verification"]["dataset_verification"]["status"] == "not_requested"
    assert first["verification"]["dataset_verification"]["executed"] is False

    # Status check must not import torch or underthesea.
    probe_code = (
        "from pathlib import Path; import sys; "
        "from services.inference.registry import ModelRegistry; "
        "s = ModelRegistry(Path(sys.argv[1])).status('neu'); "
        "assert s['available'] is True; "
        "assert 'torch' not in sys.modules; "
        "assert 'underthesea' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", probe_code, str(model_root)], check=True)

    registry = ModelRegistry(model_root)
    neu_status = registry.status("neu")
    assert neu_status["available"] is True
    assert neu_status["model_id"] == "neu-phobert-mtl-ed-s42"
    assert neu_status["preprocessing"] == {
        "kind": "underthesea_word_tokenize",
        "equivalence": "approximate",
    }
    assert neu_status["provenance"]["oof_status"] == "reported"
    assert registry.status("uit")["available"] is False

    # Re-importing identical source is idempotent and preserves version and verification schema.
    second = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")
    assert second["status"] == "already_installed"
    assert second["model_version"] == first["model_version"]
    assert second["parity"] == first["parity"]
    assert second["verification"] == first["verification"]

    # Offline prediction with socket blocked + Vietnamese edge cases.
    orig_socket = socket.socket

    def _blocked(*args, **kwargs):
        raise RuntimeError("offline test blocked socket")

    socket.socket = _blocked
    try:
        edge_texts = [
            "Xin chào thầy cô ạ!",
            "Cơ sở vật chất phòng học A2 rất tốt 😊👍",
            unicodedata.normalize("NFD", "Trường đại học Kinh tế Quốc dân"),
            "Câu có\nnhiều dòng\nvà   khoảng trắng.",
            "Văn_bản có sẵn dấu_gạch_dưới.",
            "ko bt hnay có học ko mn ơi???",
            "Sinh viên đăng ký tín chỉ học kỳ mới gặp lỗi hệ thống đào tạo. " * 30,
        ]
        items = [{"item_id": str(i), "revision_id": f"r{i}", "text": t} for i, t in enumerate(edge_texts)]
        preds = registry.predict("neu", items)
    finally:
        socket.socket = orig_socket

    assert [p["item_id"] for p in preds] == [str(i) for i in range(len(edge_texts))]
    assert preds[-1]["truncated"] is True
    assert preds[-1]["token_count_before_truncation"] > 128
    assert preds[-1]["warnings"] == ["INPUT_TRUNCATED"]


def test_r1_prepare_phobert_config_offline_from_local_cache_and_validation(tmp_path):
    """R1: model_prepare_phobert validates pinned config fields and refuses empty offline cache."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import RobertaConfig
    from scripts.model_prepare_phobert import (EXPECTED_PHOBERT_CONFIG,
                                               prepare_phobert_config,
                                               verify_phobert_config_object)

    valid_cfg = RobertaConfig(**EXPECTED_PHOBERT_CONFIG)
    verify_phobert_config_object(valid_cfg)

    bad_cfg = RobertaConfig(**{**EXPECTED_PHOBERT_CONFIG, "hidden_size": 512})
    with pytest.raises(ValueError, match="hidden_size"):
        verify_phobert_config_object(bad_cfg)

    empty_cache = tmp_path / "empty_hub_cache"
    empty_cache.mkdir()
    with pytest.raises(RuntimeError, match="offline cache"):
        prepare_phobert_config(
            out_dir=tmp_path / "out_missing",
            local_files_only=True,
            cache_dir=empty_cache,
        )

    # Populate an isolated local HF hub cache layout with config.json only (no weights).
    snapshot_dir = empty_cache / "models--vinai--phobert-base-v2" / "snapshots" / PHOBERT_REVISION
    snapshot_dir.mkdir(parents=True)
    valid_cfg.save_pretrained(snapshot_dir)
    refs_dir = empty_cache / "models--vinai--phobert-base-v2" / "refs"
    refs_dir.mkdir(parents=True)
    (refs_dir / PHOBERT_REVISION).write_text(PHOBERT_REVISION, encoding="utf-8")

    out_dir = tmp_path / "prepared_out"
    prepared = prepare_phobert_config(
        out_dir=out_dir,
        source=None,
        local_files_only=True,
        cache_dir=empty_cache,
    )
    assert prepared["status"] == "prepared"
    assert prepared["revision"] == PHOBERT_REVISION
    assert (out_dir / "config.json").is_file()
    prov = json.loads((out_dir / "config_provenance.json").read_text(encoding="utf-8"))
    assert prov["config_sha256"] == sha256(out_dir / "config.json")
    assert prov["hidden_size"] == 768
    assert prov["vocab_size"] == 64001


def test_r2_dataset_verification_semantics_and_strict_rejection(tmp_path, monkeypatch):
    """R2: Explicit data_dir must fail on missing/invalid/misaligned data; omitted data_dir records not_requested."""
    import numpy as np

    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")

    source, cfg = _create_synthetic_phobert_source(tmp_path, monkeypatch, write_encoder_dir=True, patch_autoconfig=False)
    valid_data_dir = _create_synthetic_dataset_and_logits(tmp_path, source, cfg)
    model_root = tmp_path / "models"
    repo_root = Path(__file__).resolve().parents[2]

    # 1. Omitted data_dir -> status == "not_requested", does not claim historical or raw verification ran.
    no_data = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=None)
    dv_none = no_data["verification"]["dataset_verification"]
    assert dv_none["status"] == "not_requested"
    assert dv_none["requested"] is False
    assert dv_none["executed"] is False
    assert dv_none["passed"] is None
    assert dv_none["historical_fp16_comparison"]["executed"] is False
    assert dv_none["raw_adapter_val_comparison"]["executed"] is False
    pointer_before = (model_root / "neu" / "current.json").read_bytes()

    # 2. CLI with non-existent --data-dir must fail (nonzero exit) and never coerce to None.
    missing_dir = tmp_path / "does_not_exist"
    cli_missing = subprocess.run(
        [
            sys.executable,
            "scripts/model_import_phobert.py",
            "--source", str(source),
            "--model-root", str(model_root),
            "--profile", "neu",
            "--data-dir", str(missing_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert cli_missing.returncode != 0
    assert "does not exist" in cli_missing.stderr
    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before

    # 3. Empty data_dir must fail
    empty_dir = tmp_path / "empty_data_dir"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="missing required file"):
        import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=empty_dir)
    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before

    # 4. Tampered CSV hash must fail
    tampered_dir = tmp_path / "tampered_data"
    shutil.copytree(valid_data_dir, tampered_dir)
    (tampered_dir / "val_set_processed.csv").write_bytes((tampered_dir / "val_set_processed.csv").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=tampered_dir)
    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before

    # 5. Misaligned raw CSV (same row count, swapped labels, updated config hash) must fail alignment check
    misaligned_raw_dir = tmp_path / "misaligned_raw_data"
    shutil.copytree(valid_data_dir, misaligned_raw_dir)
    raw_lines = (misaligned_raw_dir / "val_set.csv").read_text(encoding="utf-8").splitlines()
    # Swap rows 1 and 2 in raw CSV
    swapped_raw = "\n".join([raw_lines[0], raw_lines[2], raw_lines[1], raw_lines[3], raw_lines[4]]) + "\n"
    (misaligned_raw_dir / "val_set.csv").write_bytes(swapped_raw.encode("utf-8"))
    cfg_obj = json.loads((source / "run" / "config.json").read_text(encoding="utf-8"))
    orig_cfg_text = (source / "run" / "config.json").read_text(encoding="utf-8")
    try:
        cfg_obj["raw_data_files"] = {"val_set.csv": sha256(misaligned_raw_dir / "val_set.csv")}
        (source / "run" / "config.json").write_text(json.dumps(cfg_obj, indent=2), encoding="utf-8")
        with pytest.raises(ValueError, match="not row/label aligned"):
            import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=misaligned_raw_dir)
    finally:
        (source / "run" / "config.json").write_text(orig_cfg_text, encoding="utf-8")
    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before

    # 6. Historical logits with wrong ID order must fail before publish
    orig_npz_bytes = (source / "run" / "logits.npz").read_bytes()
    try:
        npz = dict(np.load(source / "run" / "logits.npz"))
        npz["val_ids"] = npz["val_ids"][::-1]
        np.savez_compressed(source / "run" / "logits.npz", **npz)
        with pytest.raises(ValueError, match="val_ids do not match"):
            import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=valid_data_dir)
    finally:
        (source / "run" / "logits.npz").write_bytes(orig_npz_bytes)
    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before
    assert not list((model_root / "neu" / "versions").glob("_staging_*"))

    # 7. Valid data_dir succeeds and records full verification report
    verified = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=valid_data_dir)
    dv_ok = verified["verification"]["dataset_verification"]
    assert dv_ok["status"] == "passed"
    assert dv_ok["requested"] is True
    assert dv_ok["executed"] is True
    assert dv_ok["passed"] is True
    assert dv_ok["historical_fp16_comparison"]["status"] == "passed"
    assert dv_ok["raw_adapter_val_comparison"]["status"] == "passed"
    assert verified["model_version"] != no_data["model_version"]


def test_r3_reimport_verification_immutability_and_pointer_safety(tmp_path, monkeypatch):
    """R3: Re-import with new dataset runs verifier, creates immutable version, and preserves pointer on failure/verify/stage."""
    import numpy as np

    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")

    source, cfg = _create_synthetic_phobert_source(tmp_path, monkeypatch, write_encoder_dir=True, patch_autoconfig=False)
    valid_data_dir = _create_synthetic_dataset_and_logits(tmp_path, source, cfg)
    model_root = tmp_path / "models"

    eval_calls = []
    real_eval = importer_mod._evaluate_optional_data

    def _spied_eval(*args, **kwargs):
        data_inputs = args[5] if len(args) > 5 else kwargs.get("data_inputs")
        if data_inputs is not None:
            eval_calls.append(data_inputs["logits_npz_sha256"])
        return real_eval(*args, **kwargs)

    monkeypatch.setattr(importer_mod, "_evaluate_optional_data", _spied_eval)

    # 1. First import without dataset -> v1
    v1 = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu", data_dir=None)
    assert v1["status"] == "imported_and_activated"
    assert len(eval_calls) == 0
    v1_bundle = Path(v1["bundle_path"])
    v1_manifest_bytes = (v1_bundle / "manifest.json").read_bytes()

    # 2. verify-only with valid dataset does NOT write to model_root or change current.json
    verify_rep = import_phobert_checkpoint(
        source=source,
        model_root=model_root,
        profile_id="neu",
        data_dir=valid_data_dir,
        verify_only=True,
    )
    assert verify_rep["status"] == "verified_only"
    assert verify_rep["activated"] is False
    assert verify_rep["verification"]["dataset_verification"]["status"] == "passed"
    assert len(eval_calls) == 1
    assert json.loads((model_root / "neu" / "current.json").read_text(encoding="utf-8"))["version"] == v1["model_version"]
    assert len(list((model_root / "neu" / "versions").iterdir())) == 1

    # 3. stage-only with valid dataset writes v2 without changing current.json (still v1)
    staged_v2 = import_phobert_checkpoint(
        source=source,
        model_root=model_root,
        profile_id="neu",
        data_dir=valid_data_dir,
        stage_only=True,
    )
    assert staged_v2["status"] == "staged"
    assert staged_v2["activated"] is False
    assert len(eval_calls) == 2
    assert json.loads((model_root / "neu" / "current.json").read_text(encoding="utf-8"))["version"] == v1["model_version"]

    # 4. Re-import with invalid dataset fails and preserves current.json -> v1
    with pytest.raises(ValueError):
        import_phobert_checkpoint(
            source=source,
            model_root=model_root,
            profile_id="neu",
            data_dir=tmp_path / "missing_dataset",
        )
    assert json.loads((model_root / "neu" / "current.json").read_text(encoding="utf-8"))["version"] == v1["model_version"]

    # 5. Re-import with valid dataset activates v2 while keeping v1 immutable on disk
    active_v2 = import_phobert_checkpoint(
        source=source,
        model_root=model_root,
        profile_id="neu",
        data_dir=valid_data_dir,
    )
    assert active_v2["status"] == "already_installed"
    assert active_v2["activated"] is True
    assert active_v2["model_version"] == staged_v2["model_version"]
    assert active_v2["verification"]["dataset_verification"]["status"] == "passed"
    assert json.loads((model_root / "neu" / "current.json").read_text(encoding="utf-8"))["version"] == active_v2["model_version"]
    assert (v1_bundle / "manifest.json").read_bytes() == v1_manifest_bytes

    # 6. Changing a verification input (logits.npz) triggers fresh verification -> v3 (does not reuse stale v2 report)
    npz = dict(np.load(source / "run" / "logits.npz"))
    npz["val_sentiment"] = npz["val_sentiment"] + np.float32(1e-4)
    np.savez_compressed(source / "run" / "logits.npz", **npz)
    v3 = import_phobert_checkpoint(
        source=source,
        model_root=model_root,
        profile_id="neu",
        data_dir=valid_data_dir,
    )
    assert v3["status"] == "imported_and_activated"
    assert v3["model_version"] not in (v1["model_version"], active_v2["model_version"])
    assert len(eval_calls) == 3
    assert len(list((model_root / "neu" / "versions").iterdir())) == 3


@pytest.mark.parametrize("defect", [
    "missing_checkpoint",
    "seed_mismatch",
    "wrong_num_labels",
    "nan_weight",
    "vocab_plus_two_rejected",
])
def test_phobert_import_rejects_defects_without_moving_pointer(tmp_path, monkeypatch, defect):
    import torch
    from transformers import BertTokenizer, RobertaConfig

    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")

    source, _ = _create_synthetic_phobert_source(tmp_path, monkeypatch)
    model_root = tmp_path / "models"
    ok = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")
    pointer_before = (model_root / "neu" / "current.json").read_bytes()

    if defect == "missing_checkpoint":
        (source / "model.pt").unlink()
    elif defect == "seed_mismatch":
        info = json.loads((source / "model_info.json").read_text(encoding="utf-8"))
        info["seed"] = 99
        (source / "model_info.json").write_text(json.dumps(info), encoding="utf-8")
    elif defect == "wrong_num_labels":
        info = json.loads((source / "model_info.json").read_text(encoding="utf-8"))
        info["num_labels"] = {"sentiment": 3, "topic": 4}
        (source / "model_info.json").write_text(json.dumps(info), encoding="utf-8")
    elif defect == "nan_weight":
        state = torch.load(source / "model.pt", map_location="cpu", weights_only=True)
        state["out_sent.weight"][0, 0] = float("nan")
        torch.save(state, source / "model.pt")
    elif defect == "vocab_plus_two_rejected":
        import transformers
        tok = BertTokenizer.from_pretrained(str(source / "tokenizer"), use_fast=False)
        bad_cfg = RobertaConfig(
            vocab_size=len(tok) + 2,
            hidden_size=8,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=16,
            max_position_embeddings=258,
            pad_token_id=tok.pad_token_id,
        )
        monkeypatch.setattr(transformers.AutoConfig, "from_pretrained", staticmethod(lambda *a, **k: bad_cfg))

    with pytest.raises(ValueError):
        import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")

    assert (model_root / "neu" / "current.json").read_bytes() == pointer_before
    assert not list((model_root / "neu" / "versions").glob("_staging_*"))
    assert ModelRegistry(model_root).status("neu")["model_version"] == ok["model_version"]


def test_phobert_manifest_tampering_and_empty_preprocessed_output(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")

    source, _ = _create_synthetic_phobert_source(tmp_path, monkeypatch)
    model_root = tmp_path / "models"
    imported = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")
    bundle_dir = Path(imported["bundle_path"])

    # Empty output after preprocessing raises ModelUnavailable cleanly.
    import services.inference.preprocessing as prep_mod
    registry = ModelRegistry(model_root)
    monkeypatch.setattr(prep_mod.TextPreprocessor, "transform", lambda self, texts: (_ for _ in ()).throw(ValueError("Preprocessed text is empty")))
    with pytest.raises(ModelUnavailable, match="preprocessing failed"):
        registry.predict("neu", [{"item_id": "1", "revision_id": "r1", "text": "xin chào"}])
    # Preprocessing failure on a single input must not poison bundle availability.
    assert registry.status("neu")["available"] is True

    # Tampering manifest oof.audited=True is rejected.
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"]["oof"]["audited"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert ModelRegistry(model_root).status("neu")["available"] is False


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start_stack(repo_root: Path, runtime_dir: Path, env: dict[str, str], log_dir: Path, label: str):
    log_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    worker_log = (log_dir / f"worker-{label}.log").open("w", encoding="utf-8")
    api_log = (log_dir / f"api-{label}.log").open("w", encoding="utf-8")
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "services.worker", "--runtime-dir", str(runtime_dir)],
        cwd=repo_root,
        env=env,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
    )
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.api.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        cwd=repo_root,
        env=env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(100):
        try:
            health = httpx.get(f"{base_url}/api/v1/health", timeout=1.0)
            if health.is_success and health.json().get("worker", {}).get("alive"):
                return base_url, api_proc, worker_proc, api_log, worker_log
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Real API/worker ({label}) did not become healthy")


def _stop_stack(api_proc, worker_proc, api_log, worker_log) -> None:
    for proc in (api_proc, worker_proc):
        if proc is not None and proc.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            proc.wait(timeout=10)
    for handle in (api_log, worker_log):
        if handle is not None and not handle.closed:
            handle.close()


@pytest.mark.real_model
def test_real_phobert_config_rejection_and_valid_verify_only(tmp_path, monkeypatch):
    """Real 542 MB checkpoint: reject same-shape configs, then verify valid config offline."""
    import torch
    import underthesea
    from transformers import AutoConfig
    import huggingface_hub.constants as hf_constants
    import transformers.utils.hub as transformers_hub
    import services.inference.architecture as architecture

    repo_root = Path(__file__).resolve().parents[2]
    source = repo_root / "demo"
    if not (source / "model.pt").is_file():
        pytest.skip("Real demo/model.pt checkpoint not present")
    torch.set_num_threads(4)
    assert sha256(source / "model.pt") == "754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8"
    prepared = repo_root / "runtime/cache/phobert-base-v2"
    config = json.loads((prepared / "config.json").read_text(encoding="utf-8"))
    model_root = tmp_path / "models"
    empty_hf = tmp_path / "empty-hf"
    empty_hf.mkdir()
    monkeypatch.setenv("HF_HOME", str(empty_hf))
    monkeypatch.setenv("HF_HUB_CACHE", str(empty_hf / "hub"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(empty_hf / "hub"))
    monkeypatch.setattr(transformers_hub, "TRANSFORMERS_CACHE", str(empty_hf / "transformers"))

    def blocked_socket(*args, **kwargs):
        raise AssertionError("offline real checkpoint verification attempted network access")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    wrong_dir = tmp_path / "wrong-config"
    wrong_dir.mkdir()
    (wrong_dir / "config.json").write_text(json.dumps({**config, "num_attention_heads": 6}), encoding="utf-8")
    rejections = []
    for provenance in (False, True):
        if provenance:
            (wrong_dir / "config_provenance.json").write_text(json.dumps({
                "model_id": "vinai/phobert-base-v2", "revision": PHOBERT_REVISION,
                "config_sha256": sha256(wrong_dir / "config.json"),
            }), encoding="utf-8")
        with monkeypatch.context() as guard:
            guard.setattr(architecture, "build_model", lambda *a, **k: pytest.fail("wrong config reached model construction"))
            with pytest.raises(ValueError, match="num_attention_heads: expected 12, got 6") as rejected:
                import_phobert_checkpoint(source, model_root, encoder_config_dir=wrong_dir, verify_only=True)
        rejections.append({"provenance_present": provenance, "error": str(rejected.value)})
        assert not model_root.exists()
    (tmp_path / "config-rejections.json").write_text(json.dumps(rejections, indent=2), encoding="utf-8")

    report = import_phobert_checkpoint(
        source, model_root, encoder_config_dir=prepared, verify_only=True,
        report_out=tmp_path / "valid-verify-only.json",
    )
    assert report["status"] == "verified_only"
    assert report["activated"] is False
    assert report["verification"]["inference_ready"] is True
    assert report["verification"]["structural_checks"]["strict_state_dict_keys"] == 207
    assert report["parity"]["passed"] is True
    assert report["verification"]["dataset_verification"]["status"] == "not_requested"
    assert not model_root.exists()
    assert not list(empty_hf.rglob("*"))


@pytest.mark.real_model
def test_real_phobert_checkpoint_import_and_fullstack_browser_smoke(tmp_path):
    """Opt-in acceptance test: offline import, real inference, review, export, process restart, and desktop/mobile UI."""
    repo_root = Path(__file__).resolve().parents[2]
    demo_dir = repo_root / "demo"
    if not (demo_dir / "model.pt").is_file():
        pytest.skip("Real demo/model.pt checkpoint not present")
    if not (repo_root / "apps/web/dist/index.html").is_file():
        pytest.skip("Frontend build apps/web/dist/index.html not present")

    prepared_cfg_dir = repo_root / "runtime" / "cache" / "phobert-base-v2"
    if not (prepared_cfg_dir / "config.json").is_file():
        pytest.skip("Prepared local PhoBERT config runtime/cache/phobert-base-v2/config.json not present")

    from playwright.sync_api import expect, sync_playwright

    runtime_dir = tmp_path / "real-acceptance-runtime"
    model_root = runtime_dir / "models"
    empty_hf = tmp_path / "empty-hf-cache"
    empty_hf.mkdir(parents=True)
    log_dir = tmp_path / "diagnostic-logs"

    # Import real checkpoint offline using prepared local encoder config
    report = import_phobert_checkpoint(
        source=demo_dir,
        model_root=model_root,
        profile_id="neu",
        data_dir=None,
        encoder_config_dir=prepared_cfg_dir,
    )
    assert report["status"] in ("imported_and_activated", "already_installed")
    assert report["parity"]["passed"] is True
    assert report["verification"]["dataset_verification"]["status"] == "not_requested"

    env = os.environ.copy()
    env["FEEDBACK_RUNTIME"] = str(runtime_dir)
    env["HF_HOME"] = str(empty_hf)
    env["HF_HUB_CACHE"] = str(empty_hf / "hub")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONUTF8"] = "1"

    api_proc = worker_proc = api_log = worker_log = None
    try:
        base_url, api_proc, worker_proc, api_log, worker_log = _start_stack(
            repo_root, runtime_dir, env, log_dir, "run1"
        )

        profiles_resp = httpx.get(f"{base_url}/api/v1/profiles", timeout=5.0).json()
        by_id = {p["id"]: p for p in profiles_resp}
        assert by_id["neu"]["model"]["available"] is True
        assert by_id["neu"]["model"]["model_id"] == "neu-phobert-mtl-ed-s42"
        assert by_id["neu"]["model"]["model_version"] == report["model_version"]
        assert by_id["uit"]["model"]["available"] is False

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, accept_downloads=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.goto(base_url)
            expect(page.get_by_test_id("create-dataset")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

            # 1. Quick analysis with real PhoBERT checkpoint
            page.get_by_role("button", name="Thử một câu", exact=True).first.click()
            dialog = page.get_by_role("dialog", name="Thử một câu", exact=True)
            dialog.get_by_test_id("quick-input").fill("Giảng viên giảng bài rất dễ hiểu và nhiệt tình hỗ trợ sinh viên.")
            dialog.get_by_test_id("quick-analyze").click()
            expect(dialog.get_by_role("heading", name="Kết quả AI", exact=True)).to_be_visible(timeout=30000)
            expect(dialog.locator(".quick-result").get_by_text(report["model_version"])).to_be_visible()
            page.keyboard.press("Escape")

            # 2. Import Vietnamese CSV (>=2 rows with metadata) and run real batch inference
            page.get_by_test_id("create-dataset").click()
            page.get_by_test_id("dataset-name").fill("Nghiệm thu PhoBERT thật")
            csv_bytes = (
                'text;ghi_chu;don_vi\r\n'
                '"Phòng học tòa A2 hôm nay điều hòa hỏng nóng quá.";"Ghi chú 1";"Khoa QTKD"\r\n'
                '"Thầy hướng dẫn đồ án tận tâm, giải đáp chi tiết.";"Ghi chú 2";"Khoa CNTT"\r\n'
                '"Cần bổ sung thêm sách tham khảo tiếng Việt ở thư viện.";"Ghi chú 3";"Thư viện"\r\n'
            ).encode("utf-8-sig")
            page.get_by_test_id("file-upload").set_input_files(
                {"name": "neu-real.csv", "mimeType": "text/csv", "buffer": csv_bytes}
            )
            expect(page.get_by_test_id("text-column")).to_have_value("text")
            page.get_by_test_id("import-confirm").click()
            expect(page.get_by_role("heading", name="Nghiệm thu PhoBERT thật", exact=True)).to_be_visible()
            dataset_id = page.url.split("/datasets/")[-1]

            page.get_by_test_id("analyze").click()
            expect(page.get_by_text("3/3 kết quả đã lưu", exact=True)).to_be_visible(timeout=30000)

            with httpx.Client(base_url=f"{base_url}/api/v1") as client:
                items = client.get(f"/datasets/{dataset_id}/items").json()["items"]
                assert len(items) == 3
                for item in items:
                    pred = item["prediction"]
                    assert pred is not None
                    assert pred["model_id"] == "neu-phobert-mtl-ed-s42"
                    assert pred["model_version"] == report["model_version"]
                    assert pred["schema_id"] == "neu-v1"
                    assert sum(pred["sentiment"]["scores"]) == pytest.approx(1.0, abs=1e-5)
                    assert sum(pred["topic"]["scores"]) == pytest.approx(1.0, abs=1e-5)
                first_item = items[0]
                orig_sent_id = first_item["prediction"]["sentiment"]["label_id"]
                orig_topic_id = first_item["prediction"]["topic"]["label_id"]
                corrected_sent_id = (orig_sent_id + 1) % 4

                # 3. Open detail for row 1, edit sentiment independently, verify topic untouched & AI prediction intact
                page.get_by_role("button", name=first_item["text"], exact=True).click()
                expect(page.get_by_role("heading", name=f"Dòng {first_item['source_row']}", exact=True)).to_be_visible()
                page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
                page.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option(str(corrected_sent_id))
                page.get_by_label("Ghi chú cảm xúc", exact=True).fill("Đã kiểm tra nhãn thực tế")
                page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
                expect(page.get_by_text("Đã lưu · bản duyệt 1", exact=True)).to_be_visible()

                reviewed_item = client.get(f"/items/{first_item['id']}").json()
                assert reviewed_item["prediction"] == first_item["prediction"]
                assert reviewed_item["reviews"]["sentiment"]["status"] == "corrected"
                assert reviewed_item["reviews"]["sentiment"]["label_id"] == corrected_sent_id
                assert reviewed_item["reviews"]["topic"] is None
                page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

                # 4. Filter to partial review (1 row) -> export filtered CSV; then export full CSV (3 rows)
                page.get_by_label("Lọc trạng thái rà soát", exact=True).select_option("partial")
                expect(page.get_by_text("(1)", exact=True)).to_be_visible()
                page.get_by_test_id("export").click()
                page.get_by_role("button", name="Tạo bản chụp CSV", exact=True).click()
                with page.expect_download() as filtered_dl:
                    page.get_by_role("link", name="Tải CSV", exact=True).click()
                filtered_csv_path = tmp_path / "filtered-export.csv"
                filtered_dl.value.save_as(filtered_csv_path)
                filtered_raw = filtered_csv_path.read_bytes()
                assert filtered_raw.startswith(b"\xef\xbb\xbf")
                filtered_rows = list(csv.DictReader(io.StringIO(filtered_raw.decode("utf-8-sig"))))
                assert len(filtered_rows) == 1
                frow = filtered_rows[0]
                assert frow["item_id"] == first_item["id"]
                assert frow["text"] == first_item["text"]
                assert json.loads(frow["metadata"]) == {"ghi_chu": "Ghi chú 1", "don_vi": "Khoa QTKD"}
                assert frow["ai_sentiment"] == str(orig_sent_id)
                assert frow["ai_topic"] == str(orig_topic_id)
                assert frow["review_sentiment"] == str(corrected_sent_id)
                assert frow["review_sentiment_status"] == "corrected"
                assert frow["review_topic_status"] == "unreviewed"
                assert frow["effective_sentiment"] == str(corrected_sent_id)
                assert frow["effective_topic"] == str(orig_topic_id)
                assert frow["model_id"] == "neu-phobert-mtl-ed-s42"
                assert frow["model_version"] == report["model_version"]
                assert frow["run_id"] == first_item["prediction"]["run_id"]
                assert frow["revision_id"] == first_item["revision_id"]

                export_dialog = page.get_by_role("dialog", name="Xuất kết quả CSV", exact=True)
                export_dialog.locator("select").select_option("all")
                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url == f"{base_url}/api/v1/datasets/{dataset_id}/exports"
                ) as full_export_response:
                    export_dialog.get_by_role("button", name="Tạo bản chụp mới", exact=True).click()
                assert full_export_response.value.status == 201
                full_export = full_export_response.value.json()
                full_export_path = full_export["url"]
                assert full_export_path == f"/api/v1/exports/{full_export['id']}"
                assert full_export["row_count"] == 3
                full_download_link = export_dialog.get_by_role("link", name="Tải CSV", exact=True)
                expect(full_download_link).to_have_attribute("href", full_export_path)
                with page.expect_download() as full_dl:
                    full_download_link.click()
                full_csv_path = tmp_path / "full-export.csv"
                full_dl.value.save_as(full_csv_path)
                full_snapshot_bytes = full_csv_path.read_bytes()
                full_rows = list(csv.DictReader(io.StringIO(full_snapshot_bytes.decode("utf-8-sig"))))
                assert len(full_rows) == 3
                original_response = client.get(full_export_path.removeprefix("/api/v1"))
                assert original_response.status_code == 200
                assert original_response.content == full_snapshot_bytes
                export_dialog.get_by_role("button", name="Đóng", exact=True).last.click()
                page.get_by_label("Lọc trạng thái rà soát", exact=True).select_option("all")

            # 5. Restart API & worker processes on the same runtime_dir and verify persistence + new inference
            _stop_stack(api_proc, worker_proc, api_log, worker_log)
            api_proc = worker_proc = api_log = worker_log = None
            base_url2, api_proc, worker_proc, api_log, worker_log = _start_stack(
                repo_root, runtime_dir, env, log_dir, "run2"
            )

            with httpx.Client(base_url=f"{base_url2}/api/v1") as client2:
                persisted_item = client2.get(f"/items/{first_item['id']}").json()
                assert persisted_item["prediction"] == first_item["prediction"]
                assert persisted_item["reviews"]["sentiment"] == reviewed_item["reviews"]["sentiment"]
                # Fetch the exact UI-created export from the NEW server origin.
                restarted_export = httpx.get(f"{base_url2}{full_export_path}", timeout=5.0)
                assert restarted_export.status_code == 200
                assert restarted_export.headers["content-type"].startswith("text/csv")
                assert f"feedback-{full_export['id']}.csv" in restarted_export.headers["content-disposition"]
                assert restarted_export.content.startswith(b"\xef\xbb\xbf")
                assert restarted_export.content == full_snapshot_bytes
                persisted_rows = list(csv.DictReader(io.StringIO(restarted_export.content.decode("utf-8-sig"))))
                assert len(persisted_rows) == 3
                persisted_review = next(row for row in persisted_rows if row["item_id"] == first_item["id"])
                for field in (
                    "ai_sentiment", "ai_topic", "review_sentiment", "review_sentiment_status",
                    "review_topic_status", "effective_sentiment", "effective_topic",
                    "model_id", "model_version", "run_id", "revision_id",
                ):
                    assert persisted_review[field] == frow[field], field
                assert all(row["model_version"] == report["model_version"] for row in persisted_rows)
                assert all(row["schema_id"] == "neu-v1" for row in persisted_rows)

            page.goto(f"{base_url2}/#/datasets/{dataset_id}")
            expect(page.get_by_role("heading", name="Nghiệm thu PhoBERT thật", exact=True)).to_be_visible()

            # 6. Run another sentence (Quick Analysis) and a new batch item after restart
            page.get_by_role("button", name="Thử một câu", exact=True).first.click()
            dialog2 = page.get_by_role("dialog", name="Thử một câu", exact=True)
            dialog2.get_by_test_id("quick-input").fill("Thư viện yên tĩnh, nhân viên hỗ trợ sinh viên rất nhiệt tình.")
            dialog2.get_by_test_id("quick-analyze").click()
            expect(dialog2.get_by_role("heading", name="Kết quả AI", exact=True)).to_be_visible(timeout=30000)
            expect(dialog2.locator(".quick-result").get_by_text(report["model_version"])).to_be_visible()
            page.keyboard.press("Escape")

            page.locator("details.append-section summary").click()
            page.get_by_label("Phản hồi mới (mỗi dòng một câu)", exact=True).fill("Wifi ký túc xá buổi tối hơi chập chờn.")
            page.get_by_role("button", name="Thêm phản hồi", exact=True).click()
            expect(page.get_by_role("button", name="Wifi ký túc xá buổi tối hơi chập chờn.", exact=True)).to_be_visible()
            page.get_by_test_id("analyze").click()
            expect(page.get_by_text("4/4 kết quả đã lưu", exact=True)).to_be_visible(timeout=30000)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            # Adding/inferencing a fourth item cannot rewrite the old 3-row snapshot.
            snapshot_after_append = httpx.get(f"{base_url2}{full_export_path}", timeout=5.0)
            assert snapshot_after_append.status_code == 200
            assert snapshot_after_append.headers["content-type"].startswith("text/csv")
            assert snapshot_after_append.content == full_snapshot_bytes
            snapshot_rows = list(csv.DictReader(io.StringIO(snapshot_after_append.content.decode("utf-8-sig"))))
            assert len(snapshot_rows) == 3
            assert snapshot_rows == persisted_rows
            live_items = httpx.get(f"{base_url2}/api/v1/datasets/{dataset_id}/items", timeout=5.0).json()["items"]
            assert len(live_items) == 4
            (tmp_path / "export-persistence.json").write_text(json.dumps({
                "export_id": full_export["id"], "path": full_export_path,
                "original_origin": base_url, "restarted_origin": base_url2,
                "status_after_restart": restarted_export.status_code,
                "status_after_append": snapshot_after_append.status_code,
                "snapshot_sha256": sha256(full_csv_path),
                "bytes_equal_after_restart_and_append": True,
                "snapshot_rows": len(snapshot_rows), "live_rows_after_append": len(live_items),
                "reviewed_item_id": first_item["id"],
                "corrected_sentiment": corrected_sent_id, "effective_topic": orig_topic_id,
                "model_id": "neu-phobert-mtl-ed-s42", "model_version": report["model_version"],
            }, indent=2), encoding="utf-8")

            # 7. Research & Help views + Mobile 390px on a screen WITH real data/results
            page.goto(f"{base_url2}/#/research")
            expect(page.get_by_role("heading", name="Báo cáo nghiên cứu", exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

            page.goto(f"{base_url2}/#/help")
            expect(page.get_by_text(report["model_version"])).to_be_visible()
            expect(page.get_by_text("Chưa có model", exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

            mobile = browser.new_context(viewport={"width": 390, "height": 844})
            mpage = mobile.new_page()
            mpage.on("pageerror", lambda err: errors.append(str(err)))
            mpage.goto(f"{base_url2}/#/datasets/{dataset_id}")
            expect(mpage.get_by_role("heading", name="Nghiệm thu PhoBERT thật", exact=True)).to_be_visible()
            expect(mpage.get_by_role("button", name=first_item["text"], exact=True)).to_be_visible()
            assert mpage.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            mobile.close()
            ctx.close()
            browser.close()
            assert not errors
    except Exception:
        for log_file in sorted(log_dir.glob("*.log")):
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-3000:]
            print(f"\n--- {log_file.name} ---\n{tail}", file=sys.stderr)
        raise
    finally:
        _stop_stack(api_proc, worker_proc, api_log, worker_log)
