"""Offline text preprocessing adapters for ViSoBERT (raw) and PhoBERT (word-segmented)."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
from pathlib import Path
import re
import threading

UNDERTHESEA_VERSION = "9.5.0"
UNDERTHESEA_RESOURCE_DIR = "pipeline/word_tokenize/models/ws_crf_vlsp2013_20230727"
UNDERTHESEA_RESOURCE_FILES = (
    f"{UNDERTHESEA_RESOURCE_DIR}/dictionary.bin",
    f"{UNDERTHESEA_RESOURCE_DIR}/features.bin",
    f"{UNDERTHESEA_RESOURCE_DIR}/models.bin",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _underthesea_root() -> Path | None:
    spec = importlib.util.find_spec("underthesea")
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(next(iter(spec.submodule_search_locations))).resolve()


def underthesea_spec() -> dict:
    """Inspect installed underthesea package and resource hashes without importing underthesea."""
    root = _underthesea_root()
    if root is None:
        raise RuntimeError("Missing model dependency: underthesea; install requirements-model.txt")
    try:
        version = importlib.metadata.version("underthesea")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("Missing underthesea package metadata") from exc
    if version != UNDERTHESEA_VERSION:
        raise RuntimeError(f"Unsupported underthesea version {version}; expected {UNDERTHESEA_VERSION}")
    resource_hashes = {}
    for rel in UNDERTHESEA_RESOURCE_FILES:
        target = (root / rel).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise RuntimeError(f"Missing underthesea word_tokenize resource: {rel}")
        resource_hashes[rel] = _sha256(target)
    return {
        "kind": "underthesea_word_tokenize",
        "library": "underthesea",
        "library_version": version,
        "format": "text",
        "use_fast": False,
        "max_length": 128,
        "equivalence": "approximate",
        "resource_sha256": resource_hashes,
    }


def validate_preprocessing_spec(spec: dict, expected_kind: str) -> None:
    """Validate manifest preprocessing schema against expected format kind."""
    if not isinstance(spec, dict):
        raise ValueError("preprocessing metadata must be an object")
    if expected_kind == "raw":
        if spec != {"kind": "raw", "use_fast": False, "max_length": 128}:
            raise ValueError("unsupported preprocessing; raw ViSoBERT required")
        return
    if expected_kind == "underthesea_word_tokenize":
        if (spec.get("kind") != "underthesea_word_tokenize"
                or spec.get("library") != "underthesea"
                or spec.get("library_version") != UNDERTHESEA_VERSION
                or spec.get("format") != "text"
                or spec.get("use_fast") is not False
                or spec.get("max_length") != 128
                or spec.get("equivalence") != "approximate"):
            raise ValueError("unsupported PhoBERT preprocessing specification")
        resources = spec.get("resource_sha256")
        if (not isinstance(resources, dict)
                or set(resources) != set(UNDERTHESEA_RESOURCE_FILES)
                or not all(_digest(v) for v in resources.values())):
            raise ValueError("incomplete underthesea resource hash inventory")
        return
    raise ValueError(f"unsupported preprocessing kind: {expected_kind}")


def check_preprocessing_ready(spec: dict) -> None:
    """Verify local runtime readiness for the preprocessing spec without importing heavy libraries."""
    kind = spec.get("kind")
    if kind == "raw":
        return
    if kind == "underthesea_word_tokenize":
        validate_preprocessing_spec(spec, "underthesea_word_tokenize")
        actual = underthesea_spec()
        if actual["resource_sha256"] != spec["resource_sha256"]:
            raise RuntimeError("underthesea word_tokenize resource hash mismatch")
        return
    raise ValueError(f"unsupported preprocessing kind: {kind}")


class TextPreprocessor:
    """Lazy, thread-safe offline text preprocessor."""

    def __init__(self, spec: dict):
        self.spec = dict(spec)
        self._lock = threading.Lock()
        self._segmenter = None

    def _load_segmenter(self):
        if self._segmenter is not None:
            return self._segmenter
        with self._lock:
            if self._segmenter is not None:
                return self._segmenter
            check_preprocessing_ready(self.spec)
            from underthesea import word_tokenize
            self._segmenter = word_tokenize
            return self._segmenter

    def transform(self, texts: list[str]) -> list[str]:
        kind = self.spec.get("kind")
        if kind == "raw":
            out = []
            for text in texts:
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Input text must be nonblank")
                out.append(text)
            return out
        if kind == "underthesea_word_tokenize":
            segmenter = self._load_segmenter()
            out = []
            for text in texts:
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Input text must be nonblank")
                segmented = segmenter(text, format="text")
                if not isinstance(segmented, str) or not segmented.strip():
                    raise ValueError("Preprocessed text is empty")
                out.append(segmented.strip())
            return out
        raise ValueError(f"unsupported preprocessing kind: {kind}")
