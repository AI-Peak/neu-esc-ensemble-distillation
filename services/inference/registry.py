"""Lazy, offline-only loading of validated, independently versioned NEU/UIT artifacts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import threading
import time

from .preprocessing import (TextPreprocessor, check_preprocessing_ready,
                            validate_preprocessing_spec)
from .phobert_config import verify_phobert_config_object

PROFILES_PATH = Path(__file__).resolve().parents[1] / "profiles.json"
REVISION = "196a62afad9cbe4f52a54aabad828b13f0eec59a"
PHOBERT_REVISION = "86cd7fd4c148980922ac11a2cf5e257f2ba639e1"
ARCHITECTURE = "linear2head-v1"
CRITERION = "mean val macro-F1 over both tasks"


class ModelUnavailable(RuntimeError):
    """Unavailable model or failed inference call; callers must not invent results."""


class ModelIdentityChanged(ModelUnavailable):
    """Active bundle identity changed between experiment creation and pair inference."""


class _ArtifactError(ValueError):
    """A deterministic artifact configuration, tensor or schema defect."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profiles():
    return {row["id"]: row for row in json.loads(PROFILES_PATH.read_text(encoding="utf-8"))}


def label_schema(profile):
    return {task: [{"id": row["id"], "key": row["key"]} for row in profile[task]]
            for task in ("sentiment", "topic")}


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _verify_file_inventory(directory: Path, files: dict, required: set[str]) -> None:
    if not isinstance(files, dict) or not required.issubset(files) or not all(_digest(v) for v in files.values()):
        raise ValueError("incomplete artifact file hash inventory")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("artifact symlinks are forbidden")
        if path.is_file() and path.relative_to(directory).as_posix() != "manifest.json":
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(files):
        raise ValueError("artifact has missing or unlisted files")
    for relative, expected in files.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory) or sha256(path) != expected:
            raise ValueError(f"artifact integrity failure: {relative}")


def _validate_format_1(directory: Path, profile: dict, manifest: dict) -> dict:
    if manifest.get("backbone") != {"model_id": "uitnlp/visobert", "revision": REVISION}:
        raise ValueError("only the pinned ViSoBERT backbone is supported")
    validate_preprocessing_spec(manifest.get("preprocessing"), "raw")
    provenance = manifest.get("provenance", {})
    if (type(provenance.get("seed")) is not int or type(provenance.get("best_epoch")) is not int
            or provenance["best_epoch"] < 1 or provenance.get("criterion") != CRITERION
            or not _digest(provenance.get("runner_sha256"))
            or not provenance.get("benchmark_eligible")
            or not isinstance(provenance.get("selection_score"), (int, float))
            or not math.isfinite(provenance["selection_score"])):
        raise ValueError("incomplete training/epoch selection provenance")
    data = provenance.get("data_sha256", {})
    if set(data) != {"train_set.csv", "val_set.csv", "test_set.csv"} or not all(map(_digest, data.values())):
        raise ValueError("raw split SHA-256 provenance required")
    oof = provenance.get("oof", {})
    if (not _digest(oof.get("targets_sha256")) or not _digest(oof.get("validation_sha256"))
            or oof.get("train_csv_sha256") != data["train_set.csv"]
            or oof.get("source_count") != 30 or oof.get("predictions_per_row") != 6):
        raise ValueError("validated 30-teacher OOF provenance required")
    parity = manifest.get("parity", {})
    if parity.get("passed") is not True or parity.get("batch_sizes") != [1, 2, 8] or parity.get("rows", 0) < 3:
        raise ValueError("reload/batch/order parity verification required")
    files = manifest.get("files", {})
    required = {"model.safetensors", "encoder/config.json", "tokenizer/tokenizer_config.json",
                "training_config.json", "oof_validation.json", "parity.json"}
    _verify_file_inventory(directory, files, required)
    config = json.loads((directory / "training_config.json").read_text(encoding="utf-8"))
    expected_dataset = "vsfc" if profile["id"] == "uit" else "neu"
    if (config.get("dataset") != expected_dataset or config.get("backbone") != "visobert"
            or config.get("setup") != "mtl_ed" or config.get("fold") is not None
            or config.get("model_path_override") or config.get("revision") != REVISION
            or config.get("seed") != provenance["seed"] or not config.get("benchmark_eligible")
            or config.get("selection") != CRITERION or config.get("data_files") != data
            or config.get("code", {}).get("runner_sha256") != provenance["runner_sha256"]):
        raise ValueError("training config and manifest provenance disagree")
    validated_oof = json.loads((directory / "oof_validation.json").read_text(encoding="utf-8"))
    if (oof["validation_sha256"] != files["oof_validation.json"]
            or not validated_oof.get("validated") or validated_oof.get("dataset") != expected_dataset
            or any(validated_oof.get(key) != oof[key]
                   for key in ("targets_sha256", "train_csv_sha256", "source_count", "predictions_per_row"))):
        raise ValueError("OOF validation and manifest provenance disagree")
    if json.loads((directory / "parity.json").read_text(encoding="utf-8")) != parity:
        raise ValueError("parity report and manifest disagree")
    return manifest


def _validate_format_2(directory: Path, profile: dict, manifest: dict) -> dict:
    if manifest.get("backbone") != {"model_id": "vinai/phobert-base-v2", "revision": PHOBERT_REVISION}:
        raise ValueError("only the pinned PhoBERT-base-v2 backbone is supported")
    validate_preprocessing_spec(manifest.get("preprocessing"), "underthesea_word_tokenize")
    provenance = manifest.get("provenance", {})
    if (type(provenance.get("seed")) is not int or type(provenance.get("best_epoch")) is not int
            or provenance["best_epoch"] < 1 or provenance.get("criterion") != CRITERION
            or not _digest(provenance.get("original_checkpoint_sha256"))
            or not _digest(provenance.get("runner_sha256"))
            or not _digest(provenance.get("importer_sha256"))
            or provenance.get("benchmark_eligible") is not True
            or not isinstance(provenance.get("selection_score"), (int, float))
            or not math.isfinite(provenance["selection_score"])):
        raise ValueError("incomplete imported checkpoint training/epoch selection provenance")
    data = provenance.get("data_sha256", {})
    if (set(data) != {"train_set_processed.csv", "val_set_processed.csv", "test_set_processed.csv"}
            or not all(map(_digest, data.values()))):
        raise ValueError("processed split SHA-256 provenance required")
    oof = provenance.get("oof", {})
    if (oof.get("status") != "reported" or oof.get("audited") is not False
            or oof.get("source_count") != 30 or oof.get("predictions_per_row") != 6):
        raise ValueError("honest reported 30-teacher OOF provenance required (audited must be false)")
    parity = manifest.get("parity", {})
    if (parity.get("passed") is not True or parity.get("batch_sizes") != [1, 2, 8]
            or parity.get("rows", 0) < 3 or parity.get("reversed_order") is not True):
        raise ValueError("reload/batch/order parity verification required")
    verification = manifest.get("verification", {})
    if verification.get("passed") is not True:
        raise ValueError("checkpoint verification report required")
    dataset_ver = verification.get("dataset_verification")
    if isinstance(dataset_ver, dict):
        if dataset_ver.get("status") == "failed" or (
            dataset_ver.get("requested") is True and dataset_ver.get("passed") is not True
        ):
            raise ValueError("requested dataset verification did not pass")
    files = manifest.get("files", {})
    required = {
        "model.safetensors",
        "encoder/config.json",
        "tokenizer/tokenizer_config.json",
        "preprocessing.json",
        "training_config.json",
        "source_model_info.json",
        "source_metrics.json",
        "parity.json",
        "verification.json",
    }
    _verify_file_inventory(directory, files, required)
    if json.loads((directory / "preprocessing.json").read_text(encoding="utf-8")) != manifest["preprocessing"]:
        raise ValueError("preprocessing report and manifest disagree")
    config = json.loads((directory / "training_config.json").read_text(encoding="utf-8"))
    expected_dataset = "vsfc" if profile["id"] == "uit" else "neu"
    if (config.get("dataset") != expected_dataset or config.get("backbone") != "phobert"
            or config.get("setup") != "mtl_ed" or config.get("fold") is not None
            or config.get("model_path_override") or config.get("revision") != PHOBERT_REVISION
            or config.get("seed") != provenance["seed"] or not config.get("benchmark_eligible")
            or config.get("selection") != CRITERION or config.get("data_files") != data
            or config.get("code", {}).get("runner_sha256") != provenance["runner_sha256"]):
        raise ValueError("training config and manifest provenance disagree")
    model_info = json.loads((directory / "source_model_info.json").read_text(encoding="utf-8"))
    expected_num_labels = {"sentiment": len(profile["sentiment"]), "topic": len(profile["topic"])}
    if (model_info.get("backbone") != "phobert" or model_info.get("setup") != "mtl_ed"
            or model_info.get("seed") != provenance["seed"]
            or model_info.get("best_epoch") != provenance["best_epoch"]
            or model_info.get("max_length") != manifest["preprocessing"]["max_length"]
            or model_info.get("model_id") != "vinai/phobert-base-v2"
            or model_info.get("revision") != PHOBERT_REVISION
            or model_info.get("num_labels") != expected_num_labels):
        raise ValueError("source model_info and manifest provenance disagree")
    metrics = json.loads((directory / "source_metrics.json").read_text(encoding="utf-8"))
    if (metrics.get("status") != "COMPLETED" or not metrics.get("benchmark_eligible")
            or metrics.get("best_epoch") != provenance["best_epoch"]
            or metrics.get("runner_sha256") != provenance["runner_sha256"]
            or not isinstance(metrics.get("selection_score"), (int, float))
            or not math.isclose(metrics["selection_score"], provenance["selection_score"], rel_tol=1e-9, abs_tol=1e-9)):
        raise ValueError("source metrics and manifest provenance disagree")
    if json.loads((directory / "parity.json").read_text(encoding="utf-8")) != parity:
        raise ValueError("parity report and manifest disagree")
    if json.loads((directory / "verification.json").read_text(encoding="utf-8")) != verification:
        raise ValueError("verification report and manifest disagree")
    return manifest


def validate_artifact(directory, profile):
    """Validate every consumed file before any tensor/tokenizer deserialization."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    fmt = manifest.get("format_version")
    if fmt not in (1, 2) or manifest.get("architecture") != ARCHITECTURE:
        raise ValueError("unsupported artifact format or architecture")
    if manifest.get("profile") != profile["id"] or manifest.get("schema_id") != profile["schema_id"]:
        raise ValueError("profile/schema mismatch (NEU and UIT checkpoints are separate)")
    if manifest.get("labels") != label_schema(profile):
        raise ValueError("canonical label IDs/order mismatch")
    if manifest.get("setup") != "mtl_ed" or not manifest.get("model_id") or not manifest.get("model_version"):
        raise ValueError("a named fine-tuned MTL-ED student is required")
    if fmt == 1:
        return _validate_format_1(directory, profile, manifest)
    return _validate_format_2(directory, profile, manifest)


def load_artifact(directory, manifest):
    import torch
    from safetensors import SafetensorError
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoTokenizer
    from .architecture import build_model

    fmt = manifest.get("format_version", 1)
    config = AutoConfig.from_pretrained(str(directory / "encoder"), local_files_only=True,
                                        trust_remote_code=False)
    expected_model_type = "roberta" if fmt == 2 else "xlm-roberta"
    if config.model_type != expected_model_type:
        raise _ArtifactError(f"backbone requires a {expected_model_type} encoder")
    if fmt == 2:
        try:
            verify_phobert_config_object(config)
        except ValueError as exc:
            raise _ArtifactError(str(exc)) from exc
    model = build_model(config, {t: len(manifest["labels"][t]) for t in ("sentiment", "topic")})
    try:
        state = load_file(str(directory / "model.safetensors"), device="cpu")
    except SafetensorError:
        raise _ArtifactError("invalid safetensors artifact") from None
    expected = model.state_dict()
    if (set(state) != set(expected)
            or any(state[key].shape != expected[key].shape for key in expected)
            or any(not torch.isfinite(state[key]).all() for key in expected)):
        raise _ArtifactError("incompatible or non-finite encoder/head tensors")
    # Structural defects are proved above; resource/runtime failures during allocation
    # or loading remain retryable instead of invalidating unchanged healthy bundles.
    model.load_state_dict(state, strict=True)
    if fmt == 2:
        model.to("cpu").float()
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(str(directory / "tokenizer"), use_fast=False,
                                               local_files_only=True, trust_remote_code=False)
    vocab_gap = config.vocab_size - len(tokenizer)
    # Pinned ViSoBERT (format 1) has 15002 tokenizer entries and 15004 encoder embeddings;
    # pinned PhoBERT (format 2) has exact 64001 == 64001 match.
    valid_vocab = (vocab_gap == 0) if fmt == 2 else (vocab_gap in (0, 2))
    if (tokenizer.pad_token_id is None or tokenizer.pad_token_id != config.pad_token_id
            or not valid_vocab
            or min(tokenizer.get_vocab().values()) < 0
            or max(tokenizer.get_vocab().values()) >= config.vocab_size):
        raise _ArtifactError("tokenizer vocabulary/padding incompatible with encoder")
    return model, tokenizer


def run_logits(model, tokenizer, texts, batch_size=8, max_length=128, collect_model_inputs=False):
    """Length-sort batches and restore source order; returns FP32 logits and original lengths."""
    import torch
    lengths = [len(row) for row in tokenizer(texts, add_special_tokens=True, truncation=False)["input_ids"]]
    order = sorted(range(len(texts)), key=lambda i: lengths[i])
    outputs = [None] * len(texts)
    collected_inputs = [None] * len(texts) if collect_model_inputs else None
    with torch.inference_mode():
        for start in range(0, len(order), batch_size):
            indices = order[start:start + batch_size]
            tokens = tokenizer([texts[i] for i in indices], add_special_tokens=True, truncation=True,
                               max_length=max_length, padding=True, return_tensors="pt")
            logits = model(input_ids=tokens["input_ids"], attention_mask=tokens["attention_mask"])
            if len(logits) != 2 or any(not torch.isfinite(x).all() for x in logits):
                raise ValueError("model produced invalid logits")
            for j, i in enumerate(indices):
                outputs[i] = tuple(x[j].detach().float().cpu() for x in logits)
                if collect_model_inputs:
                    mask = tokens["attention_mask"][j].bool()
                    collected_inputs[i] = tuple(int(v) for v in tokens["input_ids"][j][mask].tolist())
    if collect_model_inputs:
        return outputs, lengths, collected_inputs
    return outputs, lengths


class ModelRegistry:
    def __init__(self, model_root: Path):
        self.model_root = Path(model_root)
        self._profiles = profiles()
        self._loaded = None
        self._lock = threading.RLock()
        self._validated = {}
        self._failures = {}

    def _inspect(self, profile):
        if profile not in self._profiles:
            raise ModelUnavailable(f"Unknown profile: {profile}")
        root = (self.model_root / profile).resolve()
        pointer = root / "current.json"
        if pointer.exists():
            version = json.loads(pointer.read_text(encoding="utf-8"))["version"]
            if not isinstance(version, str) or re.fullmatch(r"[A-Za-z0-9_-]+", version) is None:
                raise ValueError("invalid current artifact version")
            directory = root / "versions" / version
        else:
            directory = root
        if not directory.resolve().is_relative_to(root):
            raise ValueError("artifact path escapes profile root")
        # Stat every member to detect edits/additions, but hash large weights only after change.
        fingerprint = tuple(sorted((p.relative_to(directory).as_posix(), p.stat().st_size,
                                    p.stat().st_mtime_ns, p.is_symlink())
                                   for p in directory.rglob("*") if p.is_file() or p.is_symlink()))
        cached = self._validated.get(str(directory))
        if cached is None or cached[0] != fingerprint:
            manifest = validate_artifact(directory, self._profiles[profile])
            self._validated[str(directory)] = fingerprint, manifest
            self._failures.pop(str(directory), None)
        else:
            manifest = cached[1]
        if pointer.exists() and manifest["model_version"] != version:
            raise ValueError("current pointer and artifact version disagree")
        return directory, manifest

    def _ready_artifact(self, profile: str) -> tuple[Path, dict]:
        directory, manifest = self._inspect(profile)
        if str(directory) in self._failures:
            raise ModelUnavailable(self._failures[str(directory)])
        for dependency in ("torch", "transformers", "safetensors", "sentencepiece"):
            if importlib.util.find_spec(dependency) is None:
                raise ModelUnavailable(f"Missing model dependency: {dependency}; install requirements-model.txt")
        check_preprocessing_ready(manifest["preprocessing"])
        return directory, manifest

    @staticmethod
    def _build_execution_identity(profile: str, directory: Path, manifest: dict) -> dict:
        manifest_sha256 = sha256(directory / "manifest.json")
        preprocessing_sha256 = hashlib.sha256(
            json.dumps(
                manifest["preprocessing"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "profile": profile,
            "schema_id": manifest["schema_id"],
            "model_id": manifest["model_id"],
            "model_version": manifest["model_version"],
            "manifest_sha256": manifest_sha256,
            "preprocessing_sha256": preprocessing_sha256,
            "mode": "cpu-fp32-eval",
        }

    def execution_identity(self, profile: str) -> dict:
        try:
            with self._lock:
                directory, manifest = self._ready_artifact(profile)
                return self._build_execution_identity(profile, directory, manifest)
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable(f"Model unavailable: {exc}") from None

    def status(self, profile: str) -> dict:
        schema_id = self._profiles.get(profile, {}).get("schema_id", "unknown")
        result = dict(available=False, reason=None, model_id=None, model_version=None, schema_id=schema_id)
        try:
            with self._lock:
                directory, manifest = self._ready_artifact(profile)
                oof = manifest["provenance"]["oof"]
                result.update(
                    available=True,
                    model_id=manifest["model_id"],
                    model_version=manifest["model_version"],
                    backbone=manifest["backbone"]["model_id"],
                    setup=manifest["setup"],
                    preprocessing={
                        "kind": manifest["preprocessing"]["kind"],
                        "equivalence": manifest["preprocessing"].get("equivalence", "exact"),
                    },
                    provenance={
                        "seed": manifest["provenance"]["seed"],
                        "best_epoch": manifest["provenance"]["best_epoch"],
                        "oof_status": oof.get("status", "validated" if manifest["format_version"] == 1 else "reported"),
                    },
                )
        except Exception as exc:
            result["reason"] = f"Model unavailable: {exc}"
        return result

    def _run_inference_locked(
        self,
        profile: str,
        items: list[dict],
        *,
        expected_identity: dict | None = None,
        collect_model_inputs: bool = False,
    ) -> tuple[list[dict], dict | None, list[tuple[int, ...]] | None]:
        started = time.perf_counter()
        directory = None
        phase = "inspection"
        with self._lock:
            try:
                if expected_identity is not None:
                    directory, manifest = self._ready_artifact(profile)
                    actual_identity = self._build_execution_identity(profile, directory, manifest)
                    if actual_identity != expected_identity:
                        raise ModelIdentityChanged("Model execution identity changed before pair inference.")
                else:
                    directory, manifest = self._inspect(profile)
                    actual_identity = None

                key = (str(directory), manifest["model_version"], self._validated[str(directory)][0])
                if self._loaded is None or self._loaded[0] != key:
                    self._loaded = None  # Keep at most one encoder in memory.
                    phase = "artifact load"
                    model, tokenizer = load_artifact(directory, manifest)
                    preprocessor = TextPreprocessor(manifest["preprocessing"])
                    self._loaded = key, model, tokenizer, preprocessor
                    self._failures.pop(str(directory), None)
                _, model, tokenizer, preprocessor = self._loaded

                phase = "preprocessing"
                processed_texts = preprocessor.transform([x["text"] for x in items])

                phase = "inference"
                max_length = manifest["preprocessing"]["max_length"]
                if collect_model_inputs:
                    raw_out = run_logits(
                        model,
                        tokenizer,
                        processed_texts,
                        8,
                        max_length,
                        collect_model_inputs=True,
                    )
                    if not isinstance(raw_out, tuple) or len(raw_out) != 3:
                        raise ValueError("model input diagnostics unavailable")
                    logits, lengths, collected_inputs = raw_out
                else:
                    logits, lengths = (
                        run_logits(model, tokenizer, processed_texts)
                        if max_length == 128
                        else run_logits(model, tokenizer, processed_texts, 8, max_length)
                    )
                    collected_inputs = None

                if len(logits) != len(items) or len(lengths) != len(items):
                    raise _ArtifactError("model output row count mismatch")
                if collect_model_inputs and (
                    not isinstance(collected_inputs, list)
                    or len(collected_inputs) != len(items)
                    or any(not isinstance(seq, tuple) or len(seq) == 0 for seq in collected_inputs)
                ):
                    raise _ArtifactError("model input diagnostics unavailable")

                duration = (time.perf_counter() - started) * 1000 / len(items)
                result = []
                for item, row, count in zip(items, logits, lengths):
                    if len(row) != 2:
                        raise _ArtifactError("model output task count mismatch")
                    tasks = {}
                    for task, values in zip(("sentiment", "topic"), row):
                        if tuple(values.shape) != (len(manifest["labels"][task]),):
                            raise _ArtifactError("model output head/schema mismatch")
                        scores = values.softmax(-1).tolist()
                        tasks[task] = dict(label_id=max(range(len(scores)), key=scores.__getitem__), scores=scores)
                    result.append(dict(
                        item_id=item["item_id"],
                        revision_id=item["revision_id"],
                        model_id=manifest["model_id"],
                        model_version=manifest["model_version"],
                        schema_id=manifest["schema_id"],
                        **tasks,
                        token_count_before_truncation=count,
                        truncated=count > max_length,
                        warnings=["INPUT_TRUNCATED"] if count > max_length else [],
                        duration_ms=duration,
                    ))
                self._failures.pop(str(directory), None)
                return result, actual_identity, collected_inputs
            except ModelIdentityChanged:
                raise
            except Exception as exc:
                # Inference/tokenizer/runtime exceptions can contain raw feedback. Never expose
                # or retain their messages. Transient runtime errors must leave status retryable;
                # only proven artifact/tensor/schema defects invalidate a bundle.
                reason = f"Model {phase} failed ({type(exc).__name__})."
                if directory is not None and isinstance(exc, _ArtifactError):
                    self._failures[str(directory)] = reason
                raise ModelUnavailable(reason) from None

    def predict(self, profile: str, items: list[dict]) -> list[dict]:
        if not items:
            return []
        if any(not isinstance(x.get("text"), str) or not x["text"].strip()
               or "item_id" not in x or "revision_id" not in x for x in items):
            raise ValueError("Every inference item needs item_id, revision_id and nonblank text")
        predictions, _, _ = self._run_inference_locked(profile, items, collect_model_inputs=False)
        return predictions

    def predict_pair(self, profile: str, items: list[dict], expected_identity: dict) -> dict:
        if (
            not isinstance(items, list)
            or len(items) != 2
            or any(
                not isinstance(x, dict)
                or not isinstance(x.get("text"), str)
                or not x["text"].strip()
                or "item_id" not in x
                or "revision_id" not in x
                for x in items
            )
            or not isinstance(expected_identity, dict)
        ):
            raise ValueError("Pair inference requires 2 valid items with item_id, revision_id, nonblank text, and expected_identity")
        predictions, actual_identity, collected_inputs = self._run_inference_locked(
            profile,
            items,
            expected_identity=expected_identity,
            collect_model_inputs=True,
        )
        model_input_equal = collected_inputs[0] == collected_inputs[1]
        del collected_inputs
        return {
            "predictions": predictions,
            "execution_identity": actual_identity,
            "model_input_equal": model_input_equal,
        }
