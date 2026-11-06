"""Synthetic tiny random models test mechanics only; they are not live model evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from services.inference.registry import (CRITERION, REVISION, ModelRegistry, ModelUnavailable,
                                         sha256)


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import BertTokenizer, XLMRobertaConfig
    from services.inference.architecture import build_model
    from services.inference.export import export_selected
    torch.set_num_threads(1)
    torch.manual_seed(42)
    root = tmp_path_factory.mktemp("synthetic_random_model_only")
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "môn", "học", "tốt", "cơ", "sở", "vật", "chất", "rất", "ổn"]
    (root / "vocab.txt").write_text("\n".join(vocab), encoding="utf-8")
    tokenizer = BertTokenizer(str(root / "vocab.txt"), do_lower_case=False)
    cfg = XLMRobertaConfig(vocab_size=len(vocab) + 2, hidden_size=8, num_hidden_layers=1,
                        num_attention_heads=2, intermediate_size=16, max_position_embeddings=256,
                        pad_token_id=0, hidden_dropout_prob=0, attention_probs_dropout_prob=0)
    model = build_model(cfg, dict(sentiment=4, topic=10)).eval()
    targets = root / "synthetic_oof.npz"
    targets.write_bytes(b"synthetic test only; not valid training targets")
    data = {f"{s}_set.csv": (str(i) * 64) for i, s in enumerate(("train", "val", "test"), start=1)}
    targets.with_suffix(".validation.json").write_text(json.dumps(dict(
        validated=True, targets_sha256=sha256(targets), dataset="neu", train_csv_sha256=data["train_set.csv"],
        source_count=30, predictions_per_row=6)), encoding="utf-8")
    config = dict(backbone="visobert", setup="mtl_ed", dataset="neu", benchmark_eligible=True,
                  revision=REVISION, selection=CRITERION, seed=42, data_files=data,
                  code=dict(runner_sha256="a" * 64), environment=dict(synthetic_test_only=True))
    probes = ["môn học tốt", "cơ sở vật chất rất ổn", "tốt", "môn học " * 200]
    location = export_selected(model, tokenizer, config, dict(epoch=2, score=.5), root / "models", probes, targets)
    return root / "models", location


@pytest.fixture
def bundle(published, tmp_path):
    model_root, location = published
    shutil.copytree(model_root, tmp_path / "models")
    return tmp_path / "models", tmp_path / "models" / location.relative_to(model_root)


def test_missing_artifact_is_honest(tmp_path):
    registry = ModelRegistry(tmp_path)
    status = registry.status("neu")
    assert status["schema_id"] == "neu-v1"
    assert status["available"] is False and status["reason"]
    with pytest.raises(ModelUnavailable):
        registry.predict("neu", [dict(item_id="1", revision_id="r", text="Xin chào")])


def test_missing_status_does_not_import_torch(tmp_path):
    code = "from pathlib import Path; import sys; from services.inference.registry import ModelRegistry; ModelRegistry(Path(sys.argv[1])).status('neu'); assert 'torch' not in sys.modules"
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True)


def test_export_reload_real_logits_order_truncation(bundle):
    root, location = bundle
    registry = ModelRegistry(root)
    assert registry.status("neu")["available"] is True
    assert registry._loaded is None
    texts = ["cơ sở vật chất rất ổn", "tốt", "môn học " * 200, "môn học tốt"]
    items = [dict(item_id=str(i), revision_id="r" + str(i), text=t) for i, t in enumerate(texts)]
    out = registry.predict("neu", items)
    assert [x["item_id"] for x in out] == ["0", "1", "2", "3"]
    assert [x["revision_id"] for x in out] == ["r0", "r1", "r2", "r3"]
    for prediction in out:
        for task, size in (("sentiment", 4), ("topic", 10)):
            assert len(prediction[task]["scores"]) == size
            assert sum(prediction[task]["scores"]) == pytest.approx(1, abs=1e-6)
            assert 0 <= prediction[task]["label_id"] < size
        assert prediction["schema_id"] == "neu-v1" and prediction["duration_ms"] >= 0
    assert out[2]["truncated"] and out[2]["token_count_before_truncation"] > 128
    assert out[2]["warnings"] == ["INPUT_TRUNCATED"]
    assert not out[0]["truncated"]
    reverse = registry.predict("neu", list(reversed(items)))
    assert [x["sentiment"] for x in out] == list(reversed([x["sentiment"] for x in reverse]))
    manifest = json.loads((location / "manifest.json").read_text())
    assert manifest["parity"]["passed"] and manifest["parity"]["reversed_order"]
    assert registry.status("uit")["available"] is False


@pytest.mark.parametrize("change", ["schema", "labels", "architecture", "preprocessing", "provenance", "oof", "parity"])
def test_manifest_rejects_incompatible_bundle(bundle, change):
    root, location = bundle
    path = location / "manifest.json"
    manifest = json.loads(path.read_text())
    if change == "schema":
        manifest["schema_id"] = "uit-v1"
    elif change == "labels":
        manifest["labels"]["sentiment"].reverse()
    elif change == "architecture":
        manifest["architecture"] = "unknown"
    elif change == "preprocessing":
        manifest["preprocessing"]["kind"] = "word-segmented"
    elif change == "provenance":
        manifest["provenance"]["criterion"] = "test accuracy"
    elif change == "oof":
        manifest["provenance"]["oof"]["source_count"] = 1
    else:
        manifest["parity"]["passed"] = False
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert not ModelRegistry(root).status("neu")["available"]


def test_hash_validation_cache_invalidates(bundle):
    root, location = bundle
    registry = ModelRegistry(root)
    assert registry.status("neu")["available"]
    path = location / "model.safetensors"
    path.write_bytes(path.read_bytes() + b"corrupted")
    assert not registry.status("neu")["available"]


def test_missing_encoder_key_is_rejected_at_load(bundle):
    from safetensors.torch import load_file, save_file
    root, location = bundle
    weights = location / "model.safetensors"
    state = load_file(str(weights))
    del state["out_sent.weight"]
    save_file(state, str(weights))
    path = location / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["model.safetensors"] = sha256(weights)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = ModelRegistry(root)
    with pytest.raises(ModelUnavailable, match="artifact load failed"):
        registry.predict("neu", [dict(item_id="1", revision_id="r", text="tốt")])
    assert not registry.status("neu")["available"]


def test_no_cross_profile_reuse(bundle):
    root, _ = bundle
    shutil.copytree(root / "neu", root / "uit")
    assert not ModelRegistry(root).status("uit")["available"]


def test_traversal_pointer_is_rejected(bundle):
    root, _ = bundle
    (root / "neu" / "current.json").write_text('{"version":"../../uit"}')
    assert not ModelRegistry(root).status("neu")["available"]


@pytest.mark.parametrize("relative", ["unexpected.py", "encoder/manifest.json"])
def test_unlisted_file_rejected(bundle, relative):
    root, location = bundle
    (location / relative).write_text("# not consumed")
    assert not ModelRegistry(root).status("neu")["available"]


def test_invalid_input_and_empty_batch(tmp_path):
    registry = ModelRegistry(tmp_path)
    assert registry.predict("neu", []) == []
    with pytest.raises(ValueError):
        registry.predict("neu", [dict(text=" ")])


def test_transient_inference_failure_does_not_poison_registry(bundle, monkeypatch):
    import services.inference.registry as module
    root, _ = bundle
    registry = ModelRegistry(root)
    original = module.run_logits
    private_text = "private feedback must never appear in diagnostics"
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError(private_text)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "run_logits", fail_once)
    items = [dict(item_id="1", revision_id="r", text=private_text)]
    with pytest.raises(ModelUnavailable) as failure:
        registry.predict("neu", items)
    assert private_text not in str(failure.value)
    assert private_text not in repr(registry._failures)
    assert registry.status("neu")["available"]
    assert registry.predict("neu", items)[0]["item_id"] == "1"
    assert registry.status("neu")["available"]
    assert not registry._failures


@pytest.mark.parametrize("failure_phase", ["run_logits", "load_artifact"])
@pytest.mark.parametrize("error_type", [RuntimeError, MemoryError])
def test_worker_retry_after_transient_failure_with_separate_registries(bundle, tmp_path, monkeypatch,
                                                                    failure_phase, error_type):
    """API accepts retry using its own registry; the existing worker must then recover."""
    import services.inference.registry as module
    from services.storage.db import Store
    from services.worker import Worker

    root, _ = bundle
    api_registry, worker_registry = ModelRegistry(root), ModelRegistry(root)
    store = Store(tmp_path / "isolated_runtime")
    secret = "private worker input should not enter saved errors"
    dataset = store.create_dataset(dict(name="test only", profile="neu", items=[dict(text=secret)]))
    run = store.create_run(dataset["id"], api_registry.status("neu"))
    worker = Worker(store.runtime, registry=worker_registry)
    original = getattr(module, failure_phase)
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise error_type(secret)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, failure_phase, fail_once)
    assert worker.run_once()
    failed = store.job(run["job_id"])
    assert failed["status"] == "completed_with_errors" and failed["failed"] == 1
    assert secret not in json.dumps(failed)
    assert api_registry.status("neu")["available"]
    # Exercise the production retry path; the API's registry is independent of the worker's.
    store.retry(run["job_id"], api_registry.status("neu"))
    assert worker.run_once()
    recovered = store.job(run["job_id"])
    assert recovered["status"] == "completed"
    assert recovered["completed"] == 1 and recovered["failed"] == 0 and recovered["errors"] == []
    assert len(calls) == 2
    assert worker_registry.status("neu")["available"]
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM predictions WHERE run_id=?", (run["id"],)).fetchone()[0] == 1


def test_runtime_head_mismatch_still_blocks_artifact(bundle, monkeypatch):
    import torch
    import services.inference.registry as module
    root, _ = bundle
    registry = ModelRegistry(root)
    monkeypatch.setattr(module, "run_logits", lambda *args: ([(torch.zeros(3), torch.zeros(10))], [3]))
    with pytest.raises(ModelUnavailable):
        registry.predict("neu", [dict(item_id="1", revision_id="r", text="tốt")])
    assert not registry.status("neu")["available"]


def test_failed_parity_never_replaces_current(published, monkeypatch):
    import services.inference.export as exporter
    from services.inference.registry import load_artifact
    root, location = published
    manifest = json.loads((location / "manifest.json").read_text())
    model, tokenizer = load_artifact(location, manifest)
    config = json.loads((location / "training_config.json").read_text())
    pointer = root / "neu" / "current.json"
    before = pointer.read_bytes()
    def fail(*args):
        raise AssertionError("intentional synthetic parity mismatch")
    monkeypatch.setattr(exporter, "verify_parity", fail)
    with pytest.raises(AssertionError, match="parity mismatch"):
        exporter.export_selected(model, tokenizer, config, dict(epoch=2, score=.5), root,
                                 ["môn học tốt", "tốt", "cơ sở"], root.parent / "synthetic_oof.npz")
    assert pointer.read_bytes() == before
    assert not list((root / "neu" / "versions").glob("_staging_*"))


def test_cached_real_tokenizer_with_tiny_random_encoder(tmp_path):
    """Optional local resource probe: real tokenizer, random tiny encoder, no trained weights."""
    import torch
    from safetensors.torch import save_file
    from transformers import AutoConfig, AutoTokenizer, XLMRobertaConfig
    from services.inference.architecture import build_model
    from services.inference.export import verify_parity
    from services.inference.registry import load_artifact
    try:
        actual = AutoConfig.from_pretrained("uitnlp/visobert", revision=REVISION,
                                             local_files_only=True, trust_remote_code=False)
        tokenizer = AutoTokenizer.from_pretrained("uitnlp/visobert", revision=REVISION,
                                                   use_fast=False, local_files_only=True,
                                                   trust_remote_code=False)
    except OSError:
        pytest.skip("pinned ViSoBERT tokenizer/config absent locally; no download permitted")
    assert actual.model_type == "xlm-roberta"
    assert actual.vocab_size == 15004 and len(tokenizer) == 15002
    config = XLMRobertaConfig(vocab_size=actual.vocab_size, hidden_size=8, num_hidden_layers=1,
                             num_attention_heads=2, intermediate_size=16, max_position_embeddings=256,
                             pad_token_id=tokenizer.pad_token_id, hidden_dropout_prob=0,
                             attention_probs_dropout_prob=0)
    model = build_model(config, dict(sentiment=4, topic=10)).eval()
    config.save_pretrained(tmp_path / "encoder")
    tokenizer.save_pretrained(tmp_path / "tokenizer")
    save_file({k: v.detach().contiguous() for k, v in model.state_dict().items()},
              str(tmp_path / "model.safetensors"))
    restored, saved_tokenizer = load_artifact(tmp_path, dict(labels=dict(sentiment=[0]*4, topic=[0]*10)))
    probes = ["Môn học tốt.", "Cơ sở vật chất cần cải thiện.", "Em cảm ơn thầy cô.", "sinh viên " * 200]
    assert tokenizer(probes)["input_ids"] == saved_tokenizer(probes)["input_ids"]
    assert verify_parity(model, restored, saved_tokenizer, probes)["passed"]
