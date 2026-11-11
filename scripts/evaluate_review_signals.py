"""Offline validation evaluator for experimental review signals (T05).

Runs ModelRegistry.predict on raw validation CSV pairs without modifying
production runtime, re-segmenting processed CSV text, consuming research logits,
or touching test splits.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.inference.registry import ModelRegistry, ModelUnavailable, profiles, sha256  # noqa: E402
from services.review_signals import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    evaluate_task_signal,
    load_policy,
    resolve_policy_metadata,
)

PINNED_VAL_RAW_SHA256 = "0b2567fe5374cf9b8d22de92ce71d3f9bfa036dffac46fa6f7a5650e85c81169"
PINNED_VAL_PROCESSED_SHA256 = "948578e4b92df56117fd38d8edaee8d98f11adbd38611d6faee655008adea626"

DISCLAIMER_TEXT = (
    "Descriptive offline measurement only: the NEU validation split was previously "
    "used for model epoch selection, softmax scores are uncalibrated, and thresholds "
    "in review-signals-v1 remain experimental."
)

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


class ValidationInputError(ValueError):
    """Raised when validation CSV inputs, hashes, columns, or labels fail verification."""


class ModelIdentityChangedError(RuntimeError):
    """Raised when the inspected or predicted model identity changes during evaluation."""


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_integer_label(raw_value: Any, valid_ids: set[int], field_name: str, row_number: int) -> int:
    """Parse strict finite integer strings such as '2' or '2.0' within valid_ids."""
    if not isinstance(raw_value, str):
        raise ValidationInputError(f"Row {row_number}: {field_name} label must be a string.")
    stripped = raw_value.strip()
    if not stripped or not _NUMBER_RE.fullmatch(stripped):
        raise ValidationInputError(f"Row {row_number}: invalid {field_name} label syntax {raw_value!r}.")
    try:
        dec = Decimal(stripped)
    except InvalidOperation as exc:
        raise ValidationInputError(f"Row {row_number}: unparseable {field_name} label {raw_value!r}.") from exc
    if not dec.is_finite() or dec != dec.to_integral_value():
        raise ValidationInputError(f"Row {row_number}: non-integer/non-finite {field_name} label {raw_value!r}.")
    label_id = int(dec)
    if label_id not in valid_ids:
        raise ValidationInputError(
            f"Row {row_number}: {field_name} label {label_id} outside valid profile labels {sorted(valid_ids)}."
        )
    return label_id


def _reject_test_split(path: Path, role: str) -> None:
    lowered_parts = [part.lower() for part in path.parts]
    if "test_set" in path.name.lower() or any("test_set" in p for p in lowered_parts):
        raise ValidationInputError(f"Refusing {role} path targeting test split: {path}")
    if path.suffix.lower() == ".npz":
        raise ValidationInputError(f"Refusing {role} logits archive; raw CSV required: {path}")


def _read_validation_csv(
    csv_path: Path,
    profile_obj: dict[str, Any],
    *,
    expected_sha256: str | None,
    role: str,
) -> tuple[list[dict[str, Any]], str]:
    resolved = Path(csv_path).resolve()
    _reject_test_split(resolved, role)
    if not resolved.is_file():
        raise ValidationInputError(f"{role} file not found: {resolved}")

    actual_sha256 = sha256(resolved)
    if expected_sha256 is not None:
        if not expected_sha256 or actual_sha256 != expected_sha256:
            raise ValidationInputError(
                f"{role} SHA-256 mismatch for {resolved}: expected {expected_sha256}, got {actual_sha256}"
            )

    sentiment_ids = {entry["id"] for entry in profile_obj["sentiment"]}
    topic_ids = {entry["id"] for entry in profile_obj["topic"]}

    rows: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_cols = {"text", "sentiment", "classification"}
        if not required_cols.issubset(fieldnames):
            raise ValidationInputError(
                f"{role} CSV missing required columns {sorted(required_cols)}; found {fieldnames}"
            )
        for row_num, row in enumerate(reader, start=1):
            if None in row or any(row.get(col) is None for col in required_cols):
                raise ValidationInputError(f"{role} row {row_num}: malformed CSV column count.")
            text = row["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValidationInputError(f"{role} row {row_num}: text must be non-blank.")
            s_id = parse_integer_label(row["sentiment"], sentiment_ids, "sentiment", row_num)
            t_id = parse_integer_label(row["classification"], topic_ids, "classification", row_num)
            rows.append({
                "row_number": row_num,
                "text": text,
                "sentiment": s_id,
                "topic": t_id,
            })
    if not rows:
        raise ValidationInputError(f"{role} CSV contains zero rows: {resolved}")
    return rows, actual_sha256


def load_and_verify_validation_pair(
    raw_csv_path: Path,
    processed_csv_path: Path,
    profile_obj: dict[str, Any],
    *,
    expected_raw_sha256: str | None = PINNED_VAL_RAW_SHA256,
    expected_processed_sha256: str | None = PINNED_VAL_PROCESSED_SHA256,
) -> dict[str, Any]:
    """Read, hash-verify, parse, and row-align raw & processed validation CSV pairs."""
    raw_resolved = Path(raw_csv_path).resolve()
    processed_resolved = Path(processed_csv_path).resolve()
    if raw_resolved == processed_resolved:
        raise ValidationInputError("Raw and processed validation CSV paths must point to distinct files.")

    raw_rows, raw_sha256 = _read_validation_csv(
        raw_resolved,
        profile_obj,
        expected_sha256=expected_raw_sha256,
        role="raw validation CSV",
    )
    processed_rows, processed_sha256 = _read_validation_csv(
        processed_resolved,
        profile_obj,
        expected_sha256=expected_processed_sha256,
        role="processed validation CSV",
    )
    if len(raw_rows) != len(processed_rows):
        raise ValidationInputError(
            f"Validation row count mismatch: raw={len(raw_rows)}, processed={len(processed_rows)}."
        )
    for idx, (raw_row, proc_row) in enumerate(zip(raw_rows, processed_rows), start=1):
        if (raw_row["sentiment"], raw_row["topic"]) != (proc_row["sentiment"], proc_row["topic"]):
            raise ValidationInputError(
                f"Gold label mismatch at row {idx}: "
                f"raw=({raw_row['sentiment']}, {raw_row['topic']}) vs "
                f"processed=({proc_row['sentiment']}, {proc_row['topic']})."
            )

    return {
        "rows": raw_rows,
        "raw_csv": str(raw_resolved),
        "raw_sha256": raw_sha256,
        "processed_csv": str(processed_resolved),
        "processed_sha256": processed_sha256,
        "row_count": len(raw_rows),
        "gold_alignment_verified": True,
    }


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _safe_lift(flagged_error_rate: float | None, overall_error_rate: float | None) -> float | None:
    if flagged_error_rate is None or overall_error_rate is None or overall_error_rate == 0.0:
        return None
    return flagged_error_rate / overall_error_rate


def _subset_metrics(
    records: list[dict[str, Any]],
    *,
    predicate,
    valid_count: int,
    total_errors: int,
    overall_error_rate: float | None,
) -> dict[str, Any]:
    subset = [r for r in records if predicate(r)]
    count = len(subset)
    err_count = sum(1 for r in subset if r["error"])
    err_rate = _safe_rate(err_count, count)
    return {
        "count": count,
        "fraction": _safe_rate(count, valid_count),
        "error_count": err_count,
        "error_rate": err_rate,
        "error_capture": _safe_rate(err_count, total_errors),
        "lift": _safe_lift(err_rate, overall_error_rate),
    }


def _compute_scope_summary(
    records: list[dict[str, Any]],
    *,
    total_rows: int,
    failed_count: int,
    flag_key: str,
    err_key: str,
) -> dict[str, Any]:
    valid_count = len(records)
    flagged_count = sum(1 for r in records if r[flag_key])
    unflagged_count = valid_count - flagged_count
    error_count = sum(1 for r in records if r[err_key])
    flagged_error_count = sum(1 for r in records if r[flag_key] and r[err_key])
    unflagged_error_count = error_count - flagged_error_count

    error_rate_all = _safe_rate(error_count, valid_count)
    error_rate_flagged = _safe_rate(flagged_error_count, flagged_count)
    error_rate_unflagged = _safe_rate(unflagged_error_count, unflagged_count)

    return {
        "total_rows": total_rows,
        "valid_count": valid_count,
        "failed_count": failed_count,
        "flagged_count": flagged_count,
        "unflagged_count": unflagged_count,
        "flagged_fraction": _safe_rate(flagged_count, valid_count),
        "correct_count": valid_count - error_count,
        "error_count": error_count,
        "error_rate_all": error_rate_all,
        "flagged_error_count": flagged_error_count,
        "unflagged_error_count": unflagged_error_count,
        "error_rate_flagged": error_rate_flagged,
        "error_rate_unflagged": error_rate_unflagged,
        "error_capture": _safe_rate(flagged_error_count, error_count),
        "lift": _safe_lift(error_rate_flagged, error_rate_all),
    }


def compute_signal_metrics(
    records: list[dict[str, Any]],
    profile_obj: dict[str, Any],
    *,
    failed_count: int = 0,
) -> dict[str, Any]:
    """Compute descriptive per-task, union, class, reason, and truncation metrics.

    Each valid record expects:
        gold_sentiment (int), gold_topic (int),
        pred_sentiment (int), pred_topic (int),
        sentiment_reasons (list[str]), topic_reasons (list[str]),
        sentiment_flagged (bool), topic_flagged (bool),
        truncated (bool)
    """
    valid_count = len(records)
    total_rows = valid_count + failed_count

    normalized: list[dict[str, Any]] = []
    for rec in records:
        s_err = rec["pred_sentiment"] != rec["gold_sentiment"]
        t_err = rec["pred_topic"] != rec["gold_topic"]
        s_flag = bool(rec["sentiment_flagged"])
        t_flag = bool(rec["topic_flagged"])
        normalized.append({
            **rec,
            "s_error": s_err,
            "t_error": t_err,
            "u_error": s_err or t_err,
            "s_flagged": s_flag,
            "t_flagged": t_flag,
            "u_flagged": s_flag or t_flag,
            "truncated": bool(rec["truncated"]),
        })

    metrics: dict[str, Any] = {}
    for task, flag_k, err_k, gold_k, reasons_k in (
        ("sentiment", "s_flagged", "s_error", "gold_sentiment", "sentiment_reasons"),
        ("topic", "t_flagged", "t_error", "gold_topic", "topic_reasons"),
    ):
        base = _compute_scope_summary(
            normalized,
            total_rows=total_rows,
            failed_count=failed_count,
            flag_key=flag_k,
            err_key=err_k,
        )
        task_records = [
            {"error": r[err_k], "flagged": r[flag_k], "reasons": list(r[reasons_k]), "gold": r[gold_k]}
            for r in normalized
        ]
        by_class: dict[str, Any] = {}
        for label_entry in profile_obj[task]:
            lid = label_entry["id"]
            cls_rows = [r for r in task_records if r["gold"] == lid]
            cls_gold = len(cls_rows)
            cls_flagged = sum(1 for r in cls_rows if r["flagged"])
            cls_unflagged = cls_gold - cls_flagged
            cls_err = sum(1 for r in cls_rows if r["error"])
            cls_flagged_err = sum(1 for r in cls_rows if r["flagged"] and r["error"])
            cls_unflagged_err = cls_err - cls_flagged_err
            cls_err_rate = _safe_rate(cls_err, cls_gold)
            cls_flagged_err_rate = _safe_rate(cls_flagged_err, cls_flagged)
            by_class[str(lid)] = {
                "label_id": lid,
                "key": label_entry["key"],
                "name": label_entry["name"],
                "gold_count": cls_gold,
                "flagged_count": cls_flagged,
                "flagged_fraction": _safe_rate(cls_flagged, cls_gold),
                "error_count": cls_err,
                "error_rate": cls_err_rate,
                "flagged_error_count": cls_flagged_err,
                "unflagged_error_count": cls_unflagged_err,
                "error_rate_flagged": cls_flagged_err_rate,
                "error_rate_unflagged": _safe_rate(cls_unflagged_err, cls_unflagged),
                "error_capture": _safe_rate(cls_flagged_err, cls_err),
                "lift": _safe_lift(cls_flagged_err_rate, cls_err_rate),
            }

        reason_predicates = {
            "LOW_TOP1": lambda r: "LOW_TOP1" in r["reasons"],
            "SMALL_MARGIN": lambda r: "SMALL_MARGIN" in r["reasons"],
            "LOW_TOP1_ONLY": lambda r: r["reasons"] == ["LOW_TOP1"],
            "SMALL_MARGIN_ONLY": lambda r: r["reasons"] == ["SMALL_MARGIN"],
            "LOW_TOP1+SMALL_MARGIN": lambda r: "LOW_TOP1" in r["reasons"] and "SMALL_MARGIN" in r["reasons"],
        }
        by_reason = {
            key: _subset_metrics(
                task_records,
                predicate=pred,
                valid_count=valid_count,
                total_errors=base["error_count"],
                overall_error_rate=base["error_rate_all"],
            )
            for key, pred in reason_predicates.items()
        }
        base["by_class"] = by_class
        base["by_reason"] = by_reason
        metrics[task] = base

    union_base = _compute_scope_summary(
        normalized,
        total_rows=total_rows,
        failed_count=failed_count,
        flag_key="u_flagged",
        err_key="u_error",
    )
    union_records = [
        {
            "error": r["u_error"],
            "s_flagged": r["s_flagged"],
            "t_flagged": r["t_flagged"],
            "all_reasons": set(r["sentiment_reasons"]) | set(r["topic_reasons"]),
        }
        for r in normalized
    ]
    union_predicates = {
        "LOW_TOP1": lambda r: "LOW_TOP1" in r["all_reasons"],
        "SMALL_MARGIN": lambda r: "SMALL_MARGIN" in r["all_reasons"],
        "SENTIMENT_ONLY": lambda r: r["s_flagged"] and not r["t_flagged"],
        "TOPIC_ONLY": lambda r: r["t_flagged"] and not r["s_flagged"],
        "BOTH_TASKS": lambda r: r["s_flagged"] and r["t_flagged"],
    }
    union_base["by_reason"] = {
        key: _subset_metrics(
            union_records,
            predicate=pred,
            valid_count=valid_count,
            total_errors=union_base["error_count"],
            overall_error_rate=union_base["error_rate_all"],
        )
        for key, pred in union_predicates.items()
    }
    metrics["union"] = union_base

    trunc_rows = [r for r in normalized if r["truncated"]]
    non_trunc_rows = [r for r in normalized if not r["truncated"]]
    trunc_count = len(trunc_rows)
    non_trunc_count = len(non_trunc_rows)
    truncation = {
        "valid_count": valid_count,
        "truncated_count": trunc_count,
        "non_truncated_count": non_trunc_count,
        "truncated_fraction": _safe_rate(trunc_count, valid_count),
        "truncated_and_score_flagged_union_count": sum(1 for r in trunc_rows if r["u_flagged"]),
        "truncated_and_score_clear_union_count": sum(1 for r in trunc_rows if not r["u_flagged"]),
        "sentiment_truncated_error_count": sum(1 for r in trunc_rows if r["s_error"]),
        "sentiment_truncated_error_rate": _safe_rate(sum(1 for r in trunc_rows if r["s_error"]), trunc_count),
        "sentiment_non_truncated_error_count": sum(1 for r in non_trunc_rows if r["s_error"]),
        "sentiment_non_truncated_error_rate": _safe_rate(sum(1 for r in non_trunc_rows if r["s_error"]), non_trunc_count),
        "topic_truncated_error_count": sum(1 for r in trunc_rows if r["t_error"]),
        "topic_truncated_error_rate": _safe_rate(sum(1 for r in trunc_rows if r["t_error"]), trunc_count),
        "topic_non_truncated_error_count": sum(1 for r in non_trunc_rows if r["t_error"]),
        "topic_non_truncated_error_rate": _safe_rate(sum(1 for r in non_trunc_rows if r["t_error"]), non_trunc_count),
        "union_truncated_error_count": sum(1 for r in trunc_rows if r["u_error"]),
        "union_truncated_error_rate": _safe_rate(sum(1 for r in trunc_rows if r["u_error"]), trunc_count),
        "union_non_truncated_error_count": sum(1 for r in non_trunc_rows if r["u_error"]),
        "union_non_truncated_error_rate": _safe_rate(sum(1 for r in non_trunc_rows if r["u_error"]), non_trunc_count),
    }

    return {"metrics": metrics, "truncation": truncation}


def inspect_model_identity(model_root: Path, profile_id: str, registry: Any) -> dict[str, Any]:
    """Capture strict current model identity from registry status and disk manifest/pointer."""
    status = registry.status(profile_id)
    if not isinstance(status, dict) or not status.get("available"):
        reason = status.get("reason") if isinstance(status, dict) else "Model unavailable"
        raise ModelUnavailable(reason or "Model unavailable")

    profile_dir = Path(model_root) / profile_id
    pointer_path = profile_dir / "current.json"
    pointer_sha = sha256(pointer_path) if pointer_path.is_file() else None
    bundle_dir: Path | None = None
    if pointer_path.is_file():
        pointer_data = json.loads(pointer_path.read_text(encoding="utf-8"))
        version = pointer_data.get("version")
        if not isinstance(version, str) or re.fullmatch(r"[A-Za-z0-9_-]+", version) is None:
            raise ModelUnavailable("Invalid current.json version pointer.")
        bundle_dir = profile_dir / "versions" / version
    elif (profile_dir / "manifest.json").is_file():
        bundle_dir = profile_dir

    manifest_sha = None
    checkpoint_sha = None
    original_checkpoint_sha = None
    preprocessing_spec = status.get("preprocessing")
    backbone = status.get("backbone")

    if bundle_dir is not None and (bundle_dir / "manifest.json").is_file():
        manifest_path = bundle_dir / "manifest.json"
        manifest_sha = sha256(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("model_id") != status.get("model_id")
            or manifest.get("model_version") != status.get("model_version")
            or manifest.get("schema_id") != status.get("schema_id")
        ):
            raise ModelIdentityChangedError("Manifest identity disagrees with registry status.")
        checkpoint_sha = (manifest.get("files") or {}).get("model.safetensors")
        original_checkpoint_sha = (manifest.get("provenance") or {}).get("original_checkpoint_sha256")
        preprocessing_spec = manifest.get("preprocessing")
        backbone = manifest.get("backbone")

    return {
        "profile": profile_id,
        "schema_id": status.get("schema_id"),
        "model_id": status.get("model_id"),
        "model_version": status.get("model_version"),
        "backbone": backbone,
        "bundle_dir": str(bundle_dir.resolve()) if bundle_dir is not None else None,
        "pointer_sha256": pointer_sha,
        "manifest_sha256": manifest_sha,
        "checkpoint_sha256": checkpoint_sha,
        "original_checkpoint_sha256": original_checkpoint_sha,
        "preprocessing_spec": preprocessing_spec,
        "preprocessing_sha256": _canonical_sha256(preprocessing_spec) if preprocessing_spec is not None else None,
    }


def _identity_fingerprint(identity: dict[str, Any]) -> tuple[Any, ...]:
    return (
        identity["profile"],
        identity["schema_id"],
        identity["model_id"],
        identity["model_version"],
        identity["pointer_sha256"],
        identity["manifest_sha256"],
        identity["checkpoint_sha256"],
        identity["preprocessing_sha256"],
    )


def _assert_identity_unchanged(
    expected_identity: dict[str, Any],
    model_root: Path,
    profile_id: str,
    registry: Any,
    phase: str,
) -> dict[str, Any]:
    current = inspect_model_identity(model_root, profile_id, registry)
    if _identity_fingerprint(current) != _identity_fingerprint(expected_identity):
        raise ModelIdentityChangedError(
            f"Model identity changed {phase}: expected "
            f"{expected_identity['model_id']}@{expected_identity['model_version']} "
            f"(manifest={expected_identity['manifest_sha256']}), got "
            f"{current['model_id']}@{current['model_version']} (manifest={current['manifest_sha256']})."
        )
    return current


def _assert_offline_env() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise RuntimeError(
            "Offline inference flags must be set to 1 (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1)."
        )


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for pkg in ("torch", "transformers", "safetensors", "sentencepiece", "underthesea"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    return versions


def _cpu_threads() -> int | None:
    torch_mod = sys.modules.get("torch")
    if torch_mod is not None and hasattr(torch_mod, "get_num_threads"):
        try:
            return int(torch_mod.get_num_threads())
        except Exception:
            return None
    return None


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "null"
    return f"{value * 100:.2f}%"


def _fmt_num(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "null"
    return f"{value:.{digits}f}"


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render concise Markdown summary without raw feedback text or causal claims."""
    model = report["model"]
    policy = report["policy"]
    split = report["split"]
    counts = report["counts"]
    metrics = report["metrics"]
    trunc = report["truncation"]

    lines = [
        "# Đánh giá mô tả tín hiệu rà soát trên tập validation (M2 / T05)",
        "",
        f"> **{report['disclaimer']}**",
        "",
        "## Nhận diện mô hình, policy và dữ liệu",
        "",
        f"- **Profile / Schema:** `{model['profile']}` (`{model['schema_id']}`)",
        f"- **Model:** `{model['model_id']}` / version `{model['model_version']}`",
        f"- **Manifest SHA-256:** `{model.get('manifest_sha256')}`",
        f"- **Checkpoint SHA-256:** `{model.get('checkpoint_sha256')}`",
        f"- **Preprocessing SHA-256:** `{report['preprocessing'].get('spec_sha256')}`",
        (
            f"- **Policy:** `{policy['id']}` (`experimental={policy['experimental']}`, "
            f"`hash={policy['hash']}`)"
        ),
        (
            f"- **Thresholds:** sentiment=(top1<{policy['sentiment']['top1_min']}, "
            f"margin<{policy['sentiment']['margin_min']}), "
            f"topic=(top1<{policy['topic']['top1_min']}, margin<{policy['topic']['margin_min']})"
        ),
        f"- **Validation raw:** `{split['raw_csv']}` (`sha256={split['raw_sha256']}`)",
        f"- **Validation processed:** `{split['processed_csv']}` (`sha256={split['processed_sha256']}`)",
        f"- **Số dòng:** total={counts['total_rows']}, valid={counts['valid_count']}, failed={counts['failed_count']}",
        "",
        "## Kết quả theo tác vụ và hợp (union)",
        "",
        "| Phạm vi | Hợp lệ | Lỗi | Tỷ lệ flagged | Error rate (all) | Error rate (flagged) | Error rate (unflagged) | Error capture | Lift |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scope in ("sentiment", "topic", "union"):
        m = metrics[scope]
        lines.append(
            f"| `{scope}` | {m['valid_count']} | {m['failed_count']} | {_fmt_pct(m['flagged_fraction'])} "
            f"({m['flagged_count']}/{m['valid_count']}) | {_fmt_pct(m['error_rate_all'])} | "
            f"{_fmt_pct(m['error_rate_flagged'])} | {_fmt_pct(m['error_rate_unflagged'])} | "
            f"{_fmt_pct(m['error_capture'])} | {_fmt_num(m['lift'])} |"
        )

    lines.extend([
        "",
        "## Truncation đầu vào (tách biệt khỏi tín hiệu điểm)",
        "",
        f"- **Truncated:** {trunc['truncated_count']}/{trunc['valid_count']} ({_fmt_pct(trunc['truncated_fraction'])})",
        (
            f"- **Error rate (truncated vs non-truncated):** "
            f"sentiment {_fmt_pct(trunc['sentiment_truncated_error_rate'])} vs {_fmt_pct(trunc['sentiment_non_truncated_error_rate'])}; "
            f"topic {_fmt_pct(trunc['topic_truncated_error_rate'])} vs {_fmt_pct(trunc['topic_non_truncated_error_rate'])}; "
            f"union {_fmt_pct(trunc['union_truncated_error_rate'])} vs {_fmt_pct(trunc['union_non_truncated_error_rate'])}"
        ),
        "",
        "## Lệnh và runtime",
        "",
        f"- **Command:** `{report['runtime']['command']}`",
        f"- **Offline env:** `HF_HUB_OFFLINE={report['runtime']['hf_hub_offline']}`, `TRANSFORMERS_OFFLINE={report['runtime']['transformers_offline']}`",
        "",
    ])
    return "\n".join(lines)


def _atomic_write_text(path: Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, target)


def evaluate_review_signals(
    *,
    model_root: Path,
    profile_id: str,
    validation_csv: Path,
    processed_validation_csv: Path,
    policy_path: Path,
    out_path: Path,
    markdown_out_path: Path | None = None,
    expected_raw_sha256: str | None = PINNED_VAL_RAW_SHA256,
    expected_processed_sha256: str | None = PINNED_VAL_PROCESSED_SHA256,
    batch_size: int = 64,
    registry: Any | None = None,
    command_str: str | None = None,
) -> dict[str, Any]:
    """Run offline validation inference and write descriptive metrics JSON/Markdown."""
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")

    _assert_offline_env()
    all_profiles = profiles()
    if profile_id not in all_profiles:
        raise ValueError(f"Unknown profile {profile_id!r}; expected one of {sorted(all_profiles)}")
    profile_obj = all_profiles[profile_id]

    policy = load_policy(policy_path)
    policy_meta = resolve_policy_metadata(profile_obj["schema_id"], policy)

    pair = load_and_verify_validation_pair(
        validation_csv,
        processed_validation_csv,
        profile_obj,
        expected_raw_sha256=expected_raw_sha256,
        expected_processed_sha256=expected_processed_sha256,
    )

    model_registry = registry if registry is not None else ModelRegistry(Path(model_root))
    expected_identity = inspect_model_identity(Path(model_root), profile_id, model_registry)

    started = time.perf_counter()
    valid_records: list[dict[str, Any]] = []
    failed_count = 0
    rows = pair["rows"]

    def _process_single_prediction(gold_row: dict[str, Any], pred: dict[str, Any] | None) -> bool:
        if pred is None:
            return False
        if (
            pred.get("model_id") != expected_identity["model_id"]
            or pred.get("model_version") != expected_identity["model_version"]
            or pred.get("schema_id") != expected_identity["schema_id"]
        ):
            raise ModelIdentityChangedError(
                "Prediction metadata identity differs from pinned model identity."
            )
        s_sig = evaluate_task_signal(pred, None, profile_obj, "sentiment", policy_meta["sentiment"])
        t_sig = evaluate_task_signal(pred, None, profile_obj, "topic", policy_meta["topic"])
        if s_sig["state"] == "unavailable" or t_sig["state"] == "unavailable":
            return False
        valid_records.append({
            "row_number": gold_row["row_number"],
            "gold_sentiment": gold_row["sentiment"],
            "gold_topic": gold_row["topic"],
            "pred_sentiment": pred["sentiment"]["label_id"],
            "pred_topic": pred["topic"]["label_id"],
            "sentiment_reasons": list(s_sig["reasons"]),
            "topic_reasons": list(t_sig["reasons"]),
            "sentiment_flagged": s_sig["state"] == "flagged",
            "topic_flagged": t_sig["state"] == "flagged",
            "truncated": bool(pred.get("truncated")),
        })
        return True

    for start in range(0, len(rows), batch_size):
        batch_rows = rows[start:start + batch_size]
        _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "before batch")
        batch_inputs = [
            {
                "item_id": f"val-{row['row_number']}",
                "revision_id": f"rev-{row['row_number']}",
                "text": row["text"],
            }
            for row in batch_rows
        ]
        try:
            outputs = model_registry.predict(profile_id, batch_inputs)
            _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "after batch")
            by_id = {out["item_id"]: out for out in outputs if isinstance(out, dict) and "item_id" in out}
            for row, inp in zip(batch_rows, batch_inputs):
                pred = by_id.get(inp["item_id"])
                if not _process_single_prediction(row, pred):
                    failed_count += 1
        except ModelIdentityChangedError:
            raise
        except Exception:
            _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "after batch error")
            if len(batch_rows) == 1:
                failed_count += 1
                continue
            for row, inp in zip(batch_rows, batch_inputs):
                _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "before item fallback")
                try:
                    single_outputs = model_registry.predict(profile_id, [inp])
                    _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "after item fallback")
                    pred = next((o for o in single_outputs if isinstance(o, dict) and o.get("item_id") == inp["item_id"]), None)
                    if not _process_single_prediction(row, pred):
                        failed_count += 1
                except ModelIdentityChangedError:
                    raise
                except Exception:
                    _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "after item error")
                    failed_count += 1

    _assert_identity_unchanged(expected_identity, Path(model_root), profile_id, model_registry, "at completion")
    duration_seconds = round(time.perf_counter() - started, 4)

    computed = compute_signal_metrics(valid_records, profile_obj, failed_count=failed_count)
    prep_spec = expected_identity.get("preprocessing_spec")
    resource_sha = prep_spec.get("resource_sha256") if isinstance(prep_spec, dict) else None

    report: dict[str, Any] = {
        "report_version": 1,
        "evaluation_type": "offline_validation_descriptive",
        "experimental": True,
        "policy_tuned": False,
        "disclaimer": DISCLAIMER_TEXT,
        "model": {
            "profile": expected_identity["profile"],
            "schema_id": expected_identity["schema_id"],
            "model_id": expected_identity["model_id"],
            "model_version": expected_identity["model_version"],
            "backbone": expected_identity["backbone"],
            "manifest_sha256": expected_identity["manifest_sha256"],
            "checkpoint_sha256": expected_identity["checkpoint_sha256"],
            "original_checkpoint_sha256": expected_identity["original_checkpoint_sha256"],
            "pointer_sha256": expected_identity["pointer_sha256"],
        },
        "preprocessing": {
            "kind": prep_spec.get("kind") if isinstance(prep_spec, dict) else None,
            "spec": prep_spec,
            "spec_sha256": expected_identity["preprocessing_sha256"],
            "resource_sha256": resource_sha,
        },
        "policy": policy_meta,
        "split": {
            "name": "validation",
            "gold_source": "validation_csv",
            "raw_csv": pair["raw_csv"],
            "raw_sha256": pair["raw_sha256"],
            "processed_csv": pair["processed_csv"],
            "processed_sha256": pair["processed_sha256"],
            "row_count": pair["row_count"],
            "gold_alignment_verified": pair["gold_alignment_verified"],
        },
        "runtime": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "packages": _package_versions(),
            "cpu_threads": _cpu_threads(),
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
            "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE"),
            "batch_size": batch_size,
            "duration_seconds": duration_seconds,
            "command": command_str or " ".join(sys.argv),
        },
        "counts": {
            "total_rows": pair["row_count"],
            "valid_count": len(valid_records),
            "failed_count": failed_count,
        },
        "metrics": computed["metrics"],
        "truncation": computed["truncation"],
    }

    json_payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    _atomic_write_text(Path(out_path), json_payload)
    if markdown_out_path is not None:
        _atomic_write_text(Path(markdown_out_path), render_markdown_report(report))

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True, help="Temporary/copied model root (never mutate production)")
    parser.add_argument("--profile", default="neu", help="Profile ID (default: neu)")
    parser.add_argument("--validation-csv", type=Path, default=ROOT / "data/cache/neu/val_set.csv")
    parser.add_argument("--processed-validation-csv", type=Path, default=ROOT / "data/cache/neu/val_set_processed.csv")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--out", type=Path, required=True, help="Output JSON report path")
    parser.add_argument("--markdown-out", type=Path, default=None, help="Optional Markdown summary report path")
    parser.add_argument("--expected-raw-sha256", default=PINNED_VAL_RAW_SHA256)
    parser.add_argument("--expected-processed-sha256", default=PINNED_VAL_PROCESSED_SHA256)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        evaluate_review_signals(
            model_root=args.model_root,
            profile_id=args.profile,
            validation_csv=args.validation_csv,
            processed_validation_csv=args.processed_validation_csv,
            policy_path=args.policy,
            out_path=args.out,
            markdown_out_path=args.markdown_out,
            expected_raw_sha256=args.expected_raw_sha256,
            expected_processed_sha256=args.expected_processed_sha256,
            batch_size=args.batch_size,
            command_str=" ".join([sys.executable, __file__, *(argv if argv is not None else sys.argv[1:])]),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
