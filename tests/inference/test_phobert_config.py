"""Production PhoBERT contract regressions: no tiny-config validator substitutions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

import scripts.model_import_phobert as importer
from services.inference.phobert_config import verify_phobert_config_object
from services.inference.registry import PHOBERT_REVISION, sha256


# Independent reference for the pinned revision, not derived from the candidate
# or from the production validator's expected-values dictionary.
PINNED_CONFIG = {
    "model_type": "roberta", "vocab_size": 64001, "hidden_size": 768,
    "num_hidden_layers": 12, "num_attention_heads": 12, "intermediate_size": 3072,
    "max_position_embeddings": 258, "type_vocab_size": 1, "pad_token_id": 1,
    "bos_token_id": 0, "eos_token_id": 2, "hidden_act": "gelu",
    "layer_norm_eps": 1e-5, "position_embedding_type": "absolute",
    "hidden_dropout_prob": 0.1, "attention_probs_dropout_prob": 0.1,
    "use_cache": True,
}


def _write_config(directory, changes=None):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.json"
    path.write_text(json.dumps({**PINNED_CONFIG, **(changes or {})}), encoding="utf-8")
    return path


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_f1_valid_normalized_config_and_shared_validator(tmp_path):
    from transformers import AutoConfig
    import scripts.model_prepare_phobert as preparation
    import services.inference.registry as registry

    path = _write_config(tmp_path / "encoder")
    cfg = AutoConfig.from_pretrained(path.parent, local_files_only=True, trust_remote_code=False)
    assert importer.verify_phobert_config_object is verify_phobert_config_object
    assert preparation.verify_phobert_config_object is verify_phobert_config_object
    assert registry.verify_phobert_config_object is verify_phobert_config_object
    verify_phobert_config_object(cfg)
    # Serialization adds defaults, changes formatting and descriptive metadata.
    cfg._name_or_path = "harmless/offline-location"
    cfg.architectures = ["RobertaModel"]
    cfg.save_pretrained(path.parent)
    raw = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(raw, sort_keys=True, indent=4), encoding="utf-8")
    importer._resolve_encoder_config(tmp_path / "source", path)


@pytest.mark.parametrize("field,value", [
    ("model_type", "xlm-roberta"), ("vocab_size", 64000), ("hidden_size", 384),
    ("num_hidden_layers", 6), ("num_attention_heads", 6), ("intermediate_size", 1536),
    ("max_position_embeddings", 130), ("type_vocab_size", 2), ("pad_token_id", 0),
    ("bos_token_id", 2), ("eos_token_id", 0), ("hidden_act", "relu"),
    ("layer_norm_eps", 1e-6), ("position_embedding_type", "relative_key"),
    ("hidden_dropout_prob", 0.0), ("attention_probs_dropout_prob", 0.0),
    ("is_decoder", True), ("add_cross_attention", True), ("is_encoder_decoder", True),
    ("cross_attention_hidden_size", 384), ("tie_encoder_decoder", True),
    ("use_cache", False), ("pruned_heads", {"0": [0]}), ("chunk_size_feed_forward", 2),
    ("return_dict", False), ("torchscript", True), ("output_attentions", True),
    ("output_hidden_states", True), ("_attn_implementation", "sdpa"),
])
def test_f1_forward_and_runtime_config_mismatches(tmp_path, field, value):
    path = _write_config(tmp_path / "encoder", {field: value})
    with pytest.raises(ValueError) as rejected:
        importer._resolve_encoder_config(tmp_path / "source", path.parent)
    message = str(rejected.value)
    assert f"config mismatch for {field}: expected " in message
    assert "got " in message and "model_prepare_phobert.py" in message


@pytest.mark.parametrize("resolution", ["directory", "file", "source", "cache"])
@pytest.mark.parametrize("heads", [12, 6])
def test_f1_every_resolution_path_uses_production_validator(tmp_path, monkeypatch, resolution, heads):
    from transformers import AutoConfig  # Resolve lazy imports before blocking sockets.
    import huggingface_hub.constants as hf_constants
    import transformers.utils.hub as transformers_hub

    source = tmp_path / "source"
    source.mkdir()
    cache = tmp_path / "isolated-hub"
    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(cache))
    monkeypatch.setattr(transformers_hub, "TRANSFORMERS_CACHE", str(cache))
    if resolution == "cache":
        cfg_dir = cache / "models--vinai--phobert-base-v2" / "snapshots" / PHOBERT_REVISION
        target = None
    elif resolution == "source":
        cfg_dir = source / "encoder"
        target = None
    else:
        cfg_dir = tmp_path / "explicit"
        target = cfg_dir / "config.json" if resolution == "file" else cfg_dir
    _write_config(cfg_dir, {"num_attention_heads": heads})

    def blocked(*args, **kwargs):
        raise AssertionError("config resolution attempted network access")

    monkeypatch.setattr(socket, "socket", blocked)
    if heads == 6:
        with pytest.raises(ValueError, match="num_attention_heads: expected 12, got 6"):
            importer._resolve_encoder_config(source, target)
    else:
        cfg, meta = importer._resolve_encoder_config(source, target)
        assert cfg.num_attention_heads == 12
        assert meta["source_config_sha256"] == sha256(cfg_dir / "config.json")


def test_r1_offline_config_with_empty_hf_cache(tmp_path):
    """Real production resolver, isolated empty cache, blocked network, local config."""
    cfg = _write_config(tmp_path / "encoder")
    env = os.environ.copy()
    env.update(HF_HOME=str(tmp_path / "hf"), HF_HUB_CACHE=str(tmp_path / "hf/hub"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONUTF8="1")
    code = """
import socket, sys
from pathlib import Path
from transformers import AutoConfig
from scripts.model_import_phobert import _resolve_encoder_config
socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network blocked'))
cfg, meta = _resolve_encoder_config(Path(sys.argv[2]), Path(sys.argv[1]))
assert cfg.num_attention_heads == 12
assert meta['semantic_contract'] == 'phobert-base-v2-inference-v1'
"""
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(cfg), str(tmp_path / "source")],
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("provenance", [False, True])
def test_f1_rejects_before_existing_shortcut_or_construction(tmp_path, monkeypatch, provenance):
    from tests.inference.test_phobert_import_and_preprocessing import _create_synthetic_phobert_source
    import services.inference.architecture as architecture

    # Only source metadata is synthetic. The resolver/validator under test is real.
    source, _ = _create_synthetic_phobert_source(tmp_path, patch_autoconfig=False)
    path = _write_config(tmp_path / "wrong-config", {"num_attention_heads": 6})
    if provenance:
        (path.parent / "config_provenance.json").write_text(json.dumps({
            "model_id": "vinai/phobert-base-v2", "revision": PHOBERT_REVISION,
            "config_sha256": sha256(path),
        }), encoding="utf-8")
    model_root = tmp_path / "models"
    version = model_root / "neu/versions/already-there"
    version.mkdir(parents=True)
    (version / "unchanged.bin").write_bytes(b"existing immutable bundle")
    (version.parent.parent / "current.json").write_text('{"version":"already-there"}')
    before = _snapshot(model_root)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid config reached version identity/reuse, model construction or export")

    # Guard identity calculation as well as reuse: validation must precede both.
    monkeypatch.setattr(importer, "_canonical_digest", forbidden)
    monkeypatch.setattr(importer, "validate_artifact", forbidden)
    monkeypatch.setattr(architecture, "build_model", forbidden)
    with pytest.raises(ValueError, match="num_attention_heads: expected 12, got 6"):
        importer.import_phobert_checkpoint(source, model_root, encoder_config_dir=path.parent)
    assert _snapshot(model_root) == before

    # CLI must also reject rather than merely print a warning or accept a hash.
    cli = subprocess.run([
        sys.executable, "-X", "utf8", "scripts/model_import_phobert.py",
        "--source", str(source), "--model-root", str(model_root), "--encoder-config", str(path.parent),
    ], capture_output=True, text=True)
    assert cli.returncode == 1
    assert "num_attention_heads: expected 12, got 6" in cli.stderr
    assert _snapshot(model_root) == before


@pytest.mark.parametrize("field,value", [
    ("model_id", "other/model"), ("revision", "0" * 40), ("config_sha256", "0" * 64),
])
def test_f1_existing_provenance_integrity_checks_remain(tmp_path, field, value):
    path = _write_config(tmp_path / "encoder")
    provenance = {"model_id": "vinai/phobert-base-v2", "revision": PHOBERT_REVISION,
                  "config_sha256": sha256(path)}
    provenance[field] = value
    (path.parent / "config_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance mismatch"):
        importer._resolve_encoder_config(tmp_path / "source", path.parent)


def test_r1_missing_config_preserves_pointer(tmp_path, monkeypatch):
    import transformers.utils.hub as hub
    from tests.inference.test_phobert_import_and_preprocessing import _create_synthetic_phobert_source

    source, _ = _create_synthetic_phobert_source(tmp_path, patch_autoconfig=False)
    monkeypatch.setattr(hub, "TRANSFORMERS_CACHE", str(tmp_path / "empty-cache"))
    root = tmp_path / "models"
    (root / "neu/versions/existing").mkdir(parents=True)
    (root / "neu/current.json").write_text('{"version":"existing"}')
    (root / "neu/versions/existing/keep.bin").write_bytes(b"keep existing bundle")
    before = _snapshot(root)
    with pytest.raises(ValueError, match="model_prepare_phobert.py"):
        importer.import_phobert_checkpoint(source, root)
    with pytest.raises(ValueError, match="model_prepare_phobert.py"):
        importer.import_phobert_checkpoint(source, root, encoder_config_dir=tmp_path / "missing")
    assert _snapshot(root) == before


def test_f1_preparation_rejects_wrong_semantics_without_overwriting_output(tmp_path):
    from scripts.model_prepare_phobert import prepare_phobert_config

    cache = tmp_path / "hub"
    _write_config(cache / "models--vinai--phobert-base-v2/snapshots" / PHOBERT_REVISION,
                  {"num_attention_heads": 6})
    out = tmp_path / "prepared"
    _write_config(out)
    before = _snapshot(out)
    with pytest.raises(ValueError, match="num_attention_heads: expected 12, got 6"):
        prepare_phobert_config(out, cache_dir=cache, local_files_only=True)
    assert _snapshot(out) == before


def test_f1_bundle_load_rejects_wrong_semantics_before_model_allocation(tmp_path, monkeypatch):
    import services.inference.architecture as architecture
    from services.inference.registry import load_artifact

    _write_config(tmp_path / "encoder", {"layer_norm_eps": 1e-6})

    def forbidden(*args, **kwargs):
        pytest.fail("incompatible saved config reached model allocation")

    monkeypatch.setattr(architecture, "build_model", forbidden)
    with pytest.raises(ValueError, match="layer_norm_eps: expected 1e-05, got 1e-06"):
        load_artifact(tmp_path, {"format_version": 2})


def test_config_digest_changes_do_not_imply_config_acceptance():
    assert importer._canonical_digest(PINNED_CONFIG) != importer._canonical_digest(
        {**PINNED_CONFIG, "layer_norm_eps": 1e-6}
    )
