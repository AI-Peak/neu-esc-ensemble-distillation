"""Synthetic tiny random model tests for offline sensitivity inference mechanics.

NOTE: These tests use tiny random encoders/synthetic checkpoints to verify code mechanics
(execution identity, pair parity, model swap fencing, truncation token comparison, privacy).
They are explicitly NOT real trained-model evidence.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from services.inference.registry import (
    CRITERION,
    REVISION,
    ModelIdentityChanged,
    ModelRegistry,
    ModelUnavailable,
    run_logits,
    sha256,
)
from tests.inference.test_phobert_import_and_preprocessing import (
    _allow_synthetic_config,
    _create_synthetic_phobert_source,
)


@pytest.fixture(scope="module")
def format1_bundle(tmp_path_factory):
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import BertTokenizer, XLMRobertaConfig
    from services.inference.architecture import build_model
    from services.inference.export import export_selected

    torch.set_num_threads(1)
    torch.manual_seed(42)
    root = tmp_path_factory.mktemp("synth_f1_sensitivity")
    vocab = [
        "[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]",
        "môn", "học", "tốt", "cơ", "sở", "vật", "chất", "rất", "ổn",
    ]
    (root / "vocab.txt").write_text("\n".join(vocab), encoding="utf-8")
    tokenizer = BertTokenizer(str(root / "vocab.txt"), do_lower_case=False)
    cfg = XLMRobertaConfig(
        vocab_size=len(vocab) + 2,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=16,
        max_position_embeddings=256,
        pad_token_id=0,
        hidden_dropout_prob=0.0,
        attention_probs_dropout_prob=0.0,
    )
    model = build_model(cfg, {"sentiment": 4, "topic": 10}).eval()
    targets = root / "synthetic_oof.npz"
    targets.write_bytes(b"synthetic sensitivity test only")
    data = {f"{s}_set.csv": (str(i) * 64) for i, s in enumerate(("train", "val", "test"), start=1)}
    targets.with_suffix(".validation.json").write_text(
        json.dumps(
            {
                "validated": True,
                "targets_sha256": sha256(targets),
                "dataset": "neu",
                "train_csv_sha256": data["train_set.csv"],
                "source_count": 30,
                "predictions_per_row": 6,
            }
        ),
        encoding="utf-8",
    )
    config = {
        "backbone": "visobert",
        "setup": "mtl_ed",
        "dataset": "neu",
        "benchmark_eligible": True,
        "revision": REVISION,
        "selection": CRITERION,
        "seed": 42,
        "data_files": data,
        "code": {"runner_sha256": "a" * 64},
        "environment": {"synthetic_test_only": True},
    }
    probes = ["môn học tốt", "cơ sở vật chất rất ổn", "tốt", "môn học " * 200]
    location = export_selected(model, tokenizer, config, {"epoch": 2, "score": 0.5}, root / "models", probes, targets)
    return root / "models", location, config, targets


@pytest.fixture
def f1_copy(format1_bundle, tmp_path):
    model_root, location, config, targets = format1_bundle
    copied_root = tmp_path / "models_f1"
    shutil.copytree(model_root, copied_root)
    return copied_root, copied_root / location.relative_to(model_root), config, targets


def _create_f2_bundle(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("underthesea")
    from scripts.model_import_phobert import import_phobert_checkpoint

    source, _ = _create_synthetic_phobert_source(tmp_path, monkeypatch)
    model_root = tmp_path / "models_f2"
    imported = import_phobert_checkpoint(source=source, model_root=model_root, profile_id="neu")
    return model_root, imported


def test_execution_identity_fields_and_zero_heavy_imports_in_subprocess(f1_copy, tmp_path, monkeypatch):
    f1_root, f1_loc, _, _ = f1_copy
    reg_f1 = ModelRegistry(f1_root)
    ident_f1 = reg_f1.execution_identity("neu")
    assert set(ident_f1) == {
        "profile",
        "schema_id",
        "model_id",
        "model_version",
        "manifest_sha256",
        "preprocessing_sha256",
        "mode",
    }
    assert ident_f1["profile"] == "neu"
    assert ident_f1["schema_id"] == "neu-v1"
    assert ident_f1["mode"] == "cpu-fp32-eval"
    assert ident_f1["manifest_sha256"] == sha256(f1_loc / "manifest.json")

    # Missing or corrupted bundle raises ModelUnavailable cleanly.
    with pytest.raises(ModelUnavailable):
        ModelRegistry(tmp_path / "empty_models").execution_identity("neu")
    corrupt_root = tmp_path / "corrupt_models"
    shutil.copytree(f1_root, corrupt_root)
    bad_manifest_path = corrupt_root / "neu" / "versions" / ident_f1["model_version"] / "manifest.json"
    bad_manifest = json.loads(bad_manifest_path.read_text(encoding="utf-8"))
    bad_manifest["parity"]["passed"] = False
    bad_manifest_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
    with pytest.raises(ModelUnavailable):
        ModelRegistry(corrupt_root).execution_identity("neu")

    # Fresh subprocess check: execution_identity must NOT import torch, transformers, safetensors, or underthesea.
    probe = (
        "import sys; from pathlib import Path; "
        "from services.inference.registry import ModelRegistry; "
        "ident = ModelRegistry(Path(sys.argv[1])).execution_identity('neu'); "
        "assert ident['mode'] == 'cpu-fp32-eval'; "
        "assert 'torch' not in sys.modules; "
        "assert 'transformers' not in sys.modules; "
        "assert 'safetensors' not in sys.modules; "
        "assert 'underthesea' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", probe, str(f1_root)], check=True)

    # Same no-heavy-import check on Format 2 (PhoBERT + underthesea metadata).
    f2_root, _ = _create_f2_bundle(tmp_path, monkeypatch)
    ident_f2 = ModelRegistry(f2_root).execution_identity("neu")
    assert ident_f2["profile"] == "neu" and ident_f2["mode"] == "cpu-fp32-eval"
    subprocess.run([sys.executable, "-c", probe, str(f2_root)], check=True)


def test_predict_pair_parity_with_predict_and_run_logits_default_signature(f1_copy, tmp_path, monkeypatch):
    # Format 1 parity + run_logits default 2-tuple signature.
    f1_root, f1_loc, _, _ = f1_copy
    reg1 = ModelRegistry(f1_root)
    id1 = reg1.execution_identity("neu")
    items = [
        {"item_id": "base", "revision_id": "r1", "text": "cơ sở vật chất rất ổn"},
        {"item_id": "var", "revision_id": "r2", "text": "cơ sở vật chất"},
    ]
    single1 = reg1.predict("neu", items)
    pair1 = reg1.predict_pair("neu", items, id1)
    assert pair1["execution_identity"] == id1
    assert isinstance(pair1["model_input_equal"], bool)
    assert pair1["model_input_equal"] is False
    for s_pred, p_pred in zip(single1, pair1["predictions"]):
        for key in ("item_id", "revision_id", "model_id", "model_version", "schema_id", "token_count_before_truncation", "truncated", "warnings"):
            assert p_pred[key] == s_pred[key]
        for task in ("sentiment", "topic"):
            assert p_pred[task]["label_id"] == s_pred[task]["label_id"]
            assert p_pred[task]["scores"] == pytest.approx(s_pred[task]["scores"], abs=1e-6)

    # Verify default run_logits signature remains exact 2-tuple, and collect_model_inputs strips pad tokens.
    from services.inference.registry import load_artifact

    manifest1 = json.loads((f1_loc / "manifest.json").read_text(encoding="utf-8"))
    model1, tok1 = load_artifact(f1_loc, manifest1)
    two_tuple = run_logits(model1, tok1, ["môn học tốt", "môn học rất ổn"])
    assert isinstance(two_tuple, tuple) and len(two_tuple) == 2
    three_tuple = run_logits(model1, tok1, ["môn học tốt", "môn học rất ổn"], collect_model_inputs=True)
    assert isinstance(three_tuple, tuple) and len(three_tuple) == 3
    _, _, collected = three_tuple
    assert all(tok1.pad_token_id not in seq for seq in collected)

    # Format 2 parity.
    f2_root, _ = _create_f2_bundle(tmp_path, monkeypatch)
    reg2 = ModelRegistry(f2_root)
    id2 = reg2.execution_identity("neu")
    single2 = reg2.predict("neu", items)
    pair2 = reg2.predict_pair("neu", items, id2)
    assert pair2["execution_identity"] == id2
    assert pair2["model_input_equal"] is False
    for s_pred, p_pred in zip(single2, pair2["predictions"]):
        for task in ("sentiment", "topic"):
            assert p_pred[task]["label_id"] == s_pred[task]["label_id"]
            assert p_pred[task]["scores"] == pytest.approx(s_pred[task]["scores"], abs=1e-6)


def test_cached_model_detects_manifest_edit_and_pointer_swap_before_load(f1_copy, monkeypatch):
    import services.inference.registry as reg_mod

    f1_root, f1_loc, config, targets = f1_copy
    registry = ModelRegistry(f1_root)
    id_v1 = registry.execution_identity("neu")
    items = [
        {"item_id": "b", "revision_id": "rb", "text": "môn học tốt"},
        {"item_id": "v", "revision_id": "rv", "text": "môn học"},
    ]
    # Warm in-memory _loaded cache with v1.
    registry.predict("neu", items[:1])
    assert registry._loaded is not None

    load_calls = 0
    orig_load = reg_mod.load_artifact

    def spy_load(*args, **kwargs):
        nonlocal load_calls
        load_calls += 1
        return orig_load(*args, **kwargs)

    monkeypatch.setattr(reg_mod, "load_artifact", spy_load)

    # 1. In-place manifest edit while v1 is loaded -> ModelIdentityChanged BEFORE load_artifact, zero _failures poison.
    manifest_path = f1_loc / "manifest.json"
    edited_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    edited_manifest["model_id"] = "neu-visobert-edited-id"
    manifest_path.write_text(json.dumps(edited_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ModelIdentityChanged):
        registry.predict_pair("neu", items, id_v1)
    assert load_calls == 0
    assert registry._failures == {}
    assert registry.status("neu")["available"] is True
    assert registry.status("neu")["model_id"] == "neu-visobert-edited-id"

    # 2. Swap current.json to a newly published v2 bundle while v1 was in cache -> ModelIdentityChanged BEFORE load_artifact.
    from services.inference.architecture import build_model
    from services.inference.export import export_selected
    from transformers import BertTokenizer, XLMRobertaConfig

    # Capture current v1 edited identity, warm cache, then export v2 overwriting current.json.
    id_before_swap = registry.execution_identity("neu")
    # Force cache load of current bundle using original loader briefly.
    monkeypatch.setattr(reg_mod, "load_artifact", orig_load)
    registry.predict("neu", items[:1])
    monkeypatch.setattr(reg_mod, "load_artifact", spy_load)
    load_calls = 0

    model_v2, tok_v2 = orig_load(f1_loc, edited_manifest)
    time.sleep(0.02)
    probes = ["môn học tốt", "cơ sở vật chất rất ổn", "tốt", "môn học " * 200]
    cfg_v2 = {**config, "seed": 99}
    v2_loc = export_selected(model_v2, tok_v2, cfg_v2, {"epoch": 3, "score": 0.6}, f1_root, probes, targets)
    assert v2_loc != f1_loc

    with pytest.raises(ModelIdentityChanged):
        registry.predict_pair("neu", items, id_before_swap)
    assert load_calls == 0
    assert registry._failures == {}
    status_v2 = registry.status("neu")
    assert status_v2["available"] is True
    assert status_v2["model_version"] == v2_loc.name


def test_truncation_diagnostics_tail_vs_prefix_on_format1_and_format2(f1_copy, tmp_path, monkeypatch):
    # Format 1 real tokenizer truncation comparison (>128 tokens).
    f1_root, _, _, _ = f1_copy
    reg1 = ModelRegistry(f1_root)
    id1 = reg1.execution_identity("neu")

    long_tail_base = ("môn học " * 80) + "cơ sở vật chất"
    long_tail_var = "môn học " * 80
    out_tail_1 = reg1.predict_pair(
        "neu",
        [
            {"item_id": "b1", "revision_id": "rb1", "text": long_tail_base},
            {"item_id": "v1", "revision_id": "rv1", "text": long_tail_var},
        ],
        id1,
    )
    assert out_tail_1["predictions"][0]["truncated"] is True
    assert out_tail_1["predictions"][1]["truncated"] is True
    assert out_tail_1["model_input_equal"] is True

    long_prefix_base = "cơ sở " + ("môn học " * 80)
    long_prefix_var = "môn học " * 80
    out_prefix_1 = reg1.predict_pair(
        "neu",
        [
            {"item_id": "b2", "revision_id": "rb2", "text": long_prefix_base},
            {"item_id": "v2", "revision_id": "rv2", "text": long_prefix_var},
        ],
        id1,
    )
    assert out_prefix_1["predictions"][0]["truncated"] is True
    assert out_prefix_1["predictions"][1]["truncated"] is True
    assert out_prefix_1["model_input_equal"] is False

    # Format 2 real underthesea + PhoBERT tokenizer truncation comparison (>128 tokens).
    f2_root, _ = _create_f2_bundle(tmp_path, monkeypatch)
    reg2 = ModelRegistry(f2_root)
    id2 = reg2.execution_identity("neu")

    f2_tail_base = ("cơ sở vật chất rất tốt. " * 40) + "giảng viên học tập dịch vụ."
    f2_tail_var = "cơ sở vật chất rất tốt. " * 40
    out_tail_2 = reg2.predict_pair(
        "neu",
        [
            {"item_id": "b3", "revision_id": "rb3", "text": f2_tail_base},
            {"item_id": "v3", "revision_id": "rv3", "text": f2_tail_var},
        ],
        id2,
    )
    assert out_tail_2["predictions"][0]["truncated"] is True
    assert out_tail_2["predictions"][1]["truncated"] is True
    assert out_tail_2["model_input_equal"] is True

    f2_prefix_base = "giảng viên. " + ("cơ sở vật chất rất tốt. " * 40)
    f2_prefix_var = "cơ sở vật chất rất tốt. " * 40
    out_prefix_2 = reg2.predict_pair(
        "neu",
        [
            {"item_id": "b4", "revision_id": "rb4", "text": f2_prefix_base},
            {"item_id": "v4", "revision_id": "rv4", "text": f2_prefix_var},
        ],
        id2,
    )
    assert out_prefix_2["predictions"][0]["truncated"] is True
    assert out_prefix_2["predictions"][1]["truncated"] is True
    assert out_prefix_2["model_input_equal"] is False


def test_predict_pair_invalid_inputs_and_privacy_isolation(f1_copy, monkeypatch):
    import services.inference.registry as reg_mod

    f1_root, _, _, _ = f1_copy
    registry = ModelRegistry(f1_root)
    ident = registry.execution_identity("neu")
    valid_item = {"item_id": "1", "revision_id": "r1", "text": "môn học tốt"}

    for bad_items, bad_ident in (
        ([], ident),
        ([valid_item], ident),
        ([valid_item, valid_item, valid_item], ident),
        ([valid_item, {"item_id": "2", "revision_id": "r2", "text": "   "}], ident),
        ([valid_item, {"item_id": "2", "text": "môn học"}], ident),
        ([valid_item, {"item_id": "2", "revision_id": "r2", "text": "môn học"}], "not-a-dict"),
    ):
        with pytest.raises(ValueError):
            registry.predict_pair("neu", bad_items, bad_ident)

    secret = "SECRET_PAIR_SENTENCE_TOKEN_LEAK_GUARD"
    monkeypatch.setattr(
        reg_mod,
        "run_logits",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"crashed on {secret}")),
    )
    with pytest.raises(ModelUnavailable) as exc:
        registry.predict_pair(
            "neu",
            [
                {"item_id": "b", "revision_id": "rb", "text": secret},
                {"item_id": "v", "revision_id": "rv", "text": "môn học tốt"},
            ],
            ident,
        )
    assert secret not in str(exc.value)
    assert secret not in repr(registry._failures)
    assert registry._failures == {}
