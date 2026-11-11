"""Unit tests with small synthetic fixtures for scripts/evaluate_review_signals.py (T05)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_review_signals import (  # noqa: E402
    ModelIdentityChangedError,
    ValidationInputError,
    compute_signal_metrics,
    evaluate_review_signals,
    load_and_verify_validation_pair,
    main as cli_main,
    parse_integer_label,
)
from services.inference.registry import (  # noqa: E402
    CRITERION,
    REVISION,
    ModelRegistry,
    ModelUnavailable,
    profiles,
    sha256,
)


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv_pair(
    directory: Path,
    raw_rows: list[tuple[str, str, str]],
    proc_rows: list[tuple[str, str, str]] | None = None,
    *,
    raw_name: str = "val_raw.csv",
    proc_name: str = "val_processed.csv",
) -> tuple[Path, Path, str, str]:
    import csv

    proc_rows = raw_rows if proc_rows is None else proc_rows
    raw_path = directory / raw_name
    proc_path = directory / proc_name
    for path, rows in ((raw_path, raw_rows), (proc_path, proc_rows)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["text", "sentiment", "classification"])
            writer.writerows(rows)
    return raw_path, proc_path, _sha256_path(raw_path), _sha256_path(proc_path)


class _ControlledEvalRegistry:
    """Test double with deterministic predictions and optional mid-run mutation hooks."""

    def __init__(
        self,
        predictions_by_text: dict[str, dict] | None = None,
        *,
        available: bool = True,
        model_id: str = "test-double-neu",
        model_version: str = "v1",
        on_predict=None,
    ):
        self.predictions_by_text = dict(predictions_by_text or {})
        self.available = available
        self.model_id = model_id
        self.model_version = model_version
        self.on_predict = on_predict
        self.calls: list[list[str]] = []

    def status(self, profile: str) -> dict:
        prof = profiles()[profile]
        return {
            "available": self.available,
            "reason": None if self.available else "Test artifact unavailable",
            "model_id": self.model_id,
            "model_version": self.model_version,
            "schema_id": prof["schema_id"],
            "preprocessing": {"kind": "raw", "use_fast": False, "max_length": 128},
            "backbone": {"model_id": "synthetic-test-double", "revision": "test"},
        }

    def predict(self, profile: str, items: list[dict]) -> list[dict]:
        self.calls.append([item["item_id"] for item in items])
        if self.on_predict is not None:
            self.on_predict(self, items)
        prof = profiles()[profile]
        outputs = []
        for item in items:
            spec = self.predictions_by_text.get(item["text"], {})
            if spec.get("raise"):
                raise ModelUnavailable("Simulated item inference failure")
            sent_scores = spec.get("sentiment_scores", [0.85, 0.05, 0.05, 0.05])
            topic_scores = spec.get("topic_scores", [0.82] + [0.02] * 9)
            outputs.append({
                "item_id": item["item_id"],
                "revision_id": item["revision_id"],
                "model_id": spec.get("model_id", self.model_id),
                "model_version": spec.get("model_version", self.model_version),
                "schema_id": spec.get("schema_id", prof["schema_id"]),
                "sentiment": {
                    "label_id": spec.get("sentiment_label", sent_scores.index(max(sent_scores))),
                    "scores": list(sent_scores),
                },
                "topic": {
                    "label_id": spec.get("topic_label", topic_scores.index(max(topic_scores))),
                    "scores": list(topic_scores),
                },
                "token_count_before_truncation": 150 if spec.get("truncated") else 12,
                "truncated": bool(spec.get("truncated", False)),
                "warnings": ["INPUT_TRUNCATED"] if spec.get("truncated") else [],
                "duration_ms": 0.5,
            })
        return list(reversed(outputs))


@pytest.fixture
def synthetic_neu_bundle(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import BertTokenizer, XLMRobertaConfig
    from services.inference.architecture import build_model
    from services.inference.export import export_selected

    torch.set_num_threads(1)
    torch.manual_seed(7)
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "môn", "học", "tốt", "cơ", "sở", "vật", "chất", "ổn"]
    vocab_path = tmp_path / "vocab.txt"
    vocab_path.write_text("\n".join(vocab), encoding="utf-8")
    tokenizer = BertTokenizer(str(vocab_path), do_lower_case=False)
    cfg = XLMRobertaConfig(
        vocab_size=len(vocab) + 2,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=16,
        max_position_embeddings=256,
        pad_token_id=0,
        hidden_dropout_prob=0,
        attention_probs_dropout_prob=0,
    )
    model = build_model(cfg, dict(sentiment=4, topic=10)).eval()
    targets = tmp_path / "synthetic_oof.npz"
    targets.write_bytes(b"synthetic test only")
    data = {f"{s}_set.csv": (str(i) * 64) for i, s in enumerate(("train", "val", "test"), start=1)}
    targets.with_suffix(".validation.json").write_text(
        json.dumps(
            dict(
                validated=True,
                targets_sha256=sha256(targets),
                dataset="neu",
                train_csv_sha256=data["train_set.csv"],
                source_count=30,
                predictions_per_row=6,
            )
        ),
        encoding="utf-8",
    )
    config = dict(
        backbone="visobert",
        setup="mtl_ed",
        dataset="neu",
        benchmark_eligible=True,
        revision=REVISION,
        selection=CRITERION,
        seed=42,
        data_files=data,
        code=dict(runner_sha256="a" * 64),
        environment=dict(synthetic_test_only=True),
    )
    probes = ["môn học tốt", "cơ sở vật chất ổn", "tốt", "môn học " * 80]
    model_root = tmp_path / "models"
    location = export_selected(model, tokenizer, config, dict(epoch=1, score=0.5), model_root, probes, targets)
    return model_root, location


def test_parse_integer_label_strict_bounds():
    valid_sent = {0, 1, 2, 3}
    valid_topic = set(range(10))
    assert parse_integer_label("2", valid_sent, "sentiment", 1) == 2
    assert parse_integer_label(" 2.0 ", valid_sent, "sentiment", 1) == 2
    assert parse_integer_label("0.0", valid_sent, "sentiment", 1) == 0
    assert parse_integer_label("9.0", valid_topic, "classification", 1) == 9

    for bad in ("2.5", "2.0000000000000001", "NaN", "nan", "inf", "-inf", "-1", "4", "abc", "", "   ", "1e0", "2_0"):
        with pytest.raises(ValidationInputError):
            parse_integer_label(bad, valid_sent, "sentiment", 1)
    with pytest.raises(ValidationInputError):
        parse_integer_label("10", valid_topic, "classification", 1)


def test_load_validation_pair_rejects_bad_inputs(tmp_path):
    neu = profiles()["neu"]

    raw_p, proc_p, raw_sha, proc_sha = _write_csv_pair(
        tmp_path,
        [("Phản hồi một", "0.0", "4.0"), ("Phản hồi hai", "2", "2.0")],
    )
    verified = load_and_verify_validation_pair(
        raw_p, proc_p, neu, expected_raw_sha256=raw_sha, expected_processed_sha256=proc_sha
    )
    assert verified["row_count"] == 2
    assert [(r["sentiment"], r["topic"]) for r in verified["rows"]] == [(0, 4), (2, 2)]

    # Hash mismatch
    with pytest.raises(ValidationInputError, match="SHA-256"):
        load_and_verify_validation_pair(
            raw_p, proc_p, neu, expected_raw_sha256="0" * 64, expected_processed_sha256=proc_sha
        )
    with pytest.raises(ValidationInputError, match="SHA-256"):
        load_and_verify_validation_pair(
            raw_p, proc_p, neu, expected_raw_sha256=raw_sha, expected_processed_sha256="0" * 64
        )

    # Row count mismatch
    d_count = tmp_path / "count_mismatch"
    d_count.mkdir()
    r2, p2, rs2, ps2 = _write_csv_pair(
        d_count,
        [("Một", "0", "1"), ("Hai", "1", "2")],
        [("Một_x", "0", "1")],
    )
    with pytest.raises(ValidationInputError, match="row count mismatch"):
        load_and_verify_validation_pair(r2, p2, neu, expected_raw_sha256=rs2, expected_processed_sha256=ps2)

    # Gold label alignment mismatch
    d_align = tmp_path / "align_mismatch"
    d_align.mkdir()
    r3, p3, rs3, ps3 = _write_csv_pair(
        d_align,
        [("Một", "0", "1"), ("Hai", "2", "4")],
        [("Một_x", "0", "1"), ("Hai_x", "1", "4")],
    )
    with pytest.raises(ValidationInputError, match="Gold label mismatch"):
        load_and_verify_validation_pair(r3, p3, neu, expected_raw_sha256=rs3, expected_processed_sha256=ps3)

    # Blank text rejected
    d_blank = tmp_path / "blank_text"
    d_blank.mkdir()
    r4, p4, rs4, ps4 = _write_csv_pair(d_blank, [("   ", "0", "1")])
    with pytest.raises(ValidationInputError, match="non-blank"):
        load_and_verify_validation_pair(r4, p4, neu, expected_raw_sha256=rs4, expected_processed_sha256=ps4)

    # Test split filenames refused
    d_test = tmp_path / "refuse_test"
    d_test.mkdir()
    rt, pt, rst, pst = _write_csv_pair(
        d_test,
        [("Câu kiểm", "0", "1")],
        raw_name="test_set.csv",
        proc_name="val_set_processed.csv",
    )
    with pytest.raises(ValidationInputError, match="test split"):
        load_and_verify_validation_pair(rt, pt, neu, expected_raw_sha256=rst, expected_processed_sha256=pst)


def test_compute_metrics_zero_edge_cases_and_exact_math():
    neu = profiles()["neu"]

    # 1. Zero valid rows
    empty_res = compute_signal_metrics([], neu, failed_count=3)
    for scope in ("sentiment", "topic", "union"):
        m = empty_res["metrics"][scope]
        assert m["total_rows"] == 3
        assert m["valid_count"] == 0
        assert m["failed_count"] == 3
        for rate_key in ("flagged_fraction", "error_rate_all", "error_rate_flagged", "error_rate_unflagged", "error_capture", "lift"):
            assert m[rate_key] is None

    # 2. Zero errors with flagged items -> capture=None, lift=None
    zero_err_records = [
        {
            "gold_sentiment": 0, "gold_topic": 1, "pred_sentiment": 0, "pred_topic": 1,
            "sentiment_reasons": ["LOW_TOP1"], "topic_reasons": [],
            "sentiment_flagged": True, "topic_flagged": False, "truncated": False,
        },
        {
            "gold_sentiment": 1, "gold_topic": 2, "pred_sentiment": 1, "pred_topic": 2,
            "sentiment_reasons": [], "topic_reasons": [],
            "sentiment_flagged": False, "topic_flagged": False, "truncated": True,
        },
    ]
    ze = compute_signal_metrics(zero_err_records, neu)["metrics"]
    assert ze["sentiment"]["error_count"] == 0
    assert ze["sentiment"]["error_rate_flagged"] == 0.0
    assert ze["sentiment"]["error_capture"] is None
    assert ze["sentiment"]["lift"] is None
    assert ze["topic"]["error_rate_flagged"] is None  # zero flagged topics

    # 3. Zero flags with one error -> error_rate_flagged=None, error_capture=0.0, lift=None
    zero_flag_records = [
        {
            "gold_sentiment": 0, "gold_topic": 0, "pred_sentiment": 1, "pred_topic": 0,
            "sentiment_reasons": [], "topic_reasons": [],
            "sentiment_flagged": False, "topic_flagged": False, "truncated": False,
        },
        {
            "gold_sentiment": 0, "gold_topic": 0, "pred_sentiment": 0, "pred_topic": 0,
            "sentiment_reasons": [], "topic_reasons": [],
            "sentiment_flagged": False, "topic_flagged": False, "truncated": False,
        },
    ]
    zf = compute_signal_metrics(zero_flag_records, neu)["metrics"]
    assert zf["sentiment"]["flagged_count"] == 0
    assert zf["sentiment"]["error_rate_flagged"] is None
    assert zf["sentiment"]["error_rate_unflagged"] == pytest.approx(0.5)
    assert zf["sentiment"]["error_capture"] == 0.0
    assert zf["sentiment"]["lift"] is None

    # 4. Exact hand-computed multi-row per-task vs union + by_class + by_reason + truncation
    hand_records = [
        # Row A: S flagged(LOW_TOP1+SMALL_MARGIN) & S error; T clear & T correct; truncated=False
        {
            "gold_sentiment": 2, "gold_topic": 4, "pred_sentiment": 0, "pred_topic": 4,
            "sentiment_reasons": ["LOW_TOP1", "SMALL_MARGIN"], "topic_reasons": [],
            "sentiment_flagged": True, "topic_flagged": False, "truncated": False,
        },
        # Row B: S clear & S error; T flagged(LOW_TOP1) & T correct; truncated=True
        {
            "gold_sentiment": 2, "gold_topic": 4, "pred_sentiment": 1, "pred_topic": 4,
            "sentiment_reasons": [], "topic_reasons": ["LOW_TOP1"],
            "sentiment_flagged": False, "topic_flagged": True, "truncated": True,
        },
        # Row C: S clear & S correct; T flagged(SMALL_MARGIN) & T error; truncated=False
        {
            "gold_sentiment": 1, "gold_topic": 2, "pred_sentiment": 1, "pred_topic": 3,
            "sentiment_reasons": [], "topic_reasons": ["SMALL_MARGIN"],
            "sentiment_flagged": False, "topic_flagged": True, "truncated": False,
        },
        # Row D: S clear & S correct; T clear & T correct; truncated=True (truncation does NOT count as score flag)
        {
            "gold_sentiment": 0, "gold_topic": 0, "pred_sentiment": 0, "pred_topic": 0,
            "sentiment_reasons": [], "topic_reasons": [],
            "sentiment_flagged": False, "topic_flagged": False, "truncated": True,
        },
    ]
    computed = compute_signal_metrics(hand_records, neu, failed_count=1)
    ms = computed["metrics"]["sentiment"]
    mt = computed["metrics"]["topic"]
    mu = computed["metrics"]["union"]
    tr = computed["truncation"]

    # Sentiment: total=5, valid=4, failed=1, flagged=1 (Row A), err=2 (A,B), flagged_err=1 (A)
    assert ms["total_rows"] == 5 and ms["valid_count"] == 4 and ms["failed_count"] == 1
    assert ms["flagged_fraction"] == pytest.approx(0.25)
    assert ms["error_rate_all"] == pytest.approx(0.50)
    assert ms["error_rate_flagged"] == pytest.approx(1.0)
    assert ms["error_rate_unflagged"] == pytest.approx(1 / 3)
    assert ms["error_capture"] == pytest.approx(0.50)
    assert ms["lift"] == pytest.approx(2.0)
    assert ms["by_class"]["2"]["gold_count"] == 2
    assert ms["by_class"]["2"]["error_count"] == 2
    assert ms["by_class"]["2"]["flagged_error_count"] == 1
    assert ms["by_class"]["2"]["error_capture"] == pytest.approx(0.5)
    assert ms["by_class"]["3"]["gold_count"] == 0
    assert ms["by_class"]["3"]["error_rate"] is None
    assert ms["by_reason"]["LOW_TOP1+SMALL_MARGIN"]["count"] == 1
    assert ms["by_reason"]["LOW_TOP1_ONLY"]["count"] == 0

    # Topic: flagged=2 (B,C), err=1 (C), flagged_err=1 (C)
    assert mt["flagged_fraction"] == pytest.approx(0.50)
    assert mt["error_rate_all"] == pytest.approx(0.25)
    assert mt["error_rate_flagged"] == pytest.approx(0.50)
    assert mt["error_rate_unflagged"] == pytest.approx(0.0)
    assert mt["error_capture"] == pytest.approx(1.0)
    assert mt["lift"] == pytest.approx(2.0)

    # Union: flagged=3 (A,B,C — Row D truncated is NOT flagged), err=3 (A,B,C), flagged_err=3 (A,B,C!)
    assert mu["flagged_count"] == 3 and mu["error_count"] == 3 and mu["flagged_error_count"] == 3
    assert mu["error_capture"] == pytest.approx(1.0)
    assert mu["error_rate_flagged"] == pytest.approx(1.0)
    assert mu["error_rate_unflagged"] == pytest.approx(0.0)
    assert mu["by_reason"]["SENTIMENT_ONLY"]["count"] == 1
    assert mu["by_reason"]["TOPIC_ONLY"]["count"] == 2
    assert mu["by_reason"]["BOTH_TASKS"]["count"] == 0

    # Truncation kept separate: B and D are truncated (2/4), only B errored on sentiment & union, 0 on topic
    assert tr["truncated_count"] == 2
    assert tr["truncated_fraction"] == pytest.approx(0.5)
    assert tr["sentiment_truncated_error_rate"] == pytest.approx(0.5)
    assert tr["topic_truncated_error_rate"] == pytest.approx(0.0)
    assert tr["union_truncated_error_rate"] == pytest.approx(0.5)
    assert tr["truncated_and_score_clear_union_count"] == 1


def test_evaluate_handles_partial_failure_honestly_and_redacts_raw_text(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    secret_phrases = [
        "SECRET_ALPHA nội dung riêng tư",
        "SECRET_BETA sinh viên phản ánh",
        "SECRET_GAMMA đoạn bị lỗi",
        "SECRET_DELTA phản hồi sạch",
    ]
    raw_p, proc_p, raw_sha, proc_sha = _write_csv_pair(
        tmp_path,
        [
            (secret_phrases[0], "2.0", "4.0"),
            (secret_phrases[1], "1.0", "2.0"),
            (secret_phrases[2], "0.0", "0.0"),
            (secret_phrases[3], "0.0", "0.0"),
        ],
    )
    reg = _ControlledEvalRegistry({
        secret_phrases[0]: {
            "sentiment_label": 2,
            "sentiment_scores": [0.35, 0.10, 0.50, 0.05],  # top1=0.50 < 0.60, margin=0.15 -> LOW_TOP1
            "topic_label": 4,
            "topic_scores": [0.02] * 4 + [0.82] + [0.02] * 5,
        },
        secret_phrases[1]: {
            "sentiment_label": 1,
            "sentiment_scores": [0.05, 0.85, 0.05, 0.05],
            "topic_label": 2,
            "topic_scores": [0.02] * 2 + [0.82] + [0.02] * 7,
            "truncated": True,
        },
        secret_phrases[2]: {"raise": True},
        secret_phrases[3]: {
            "sentiment_label": 0,
            "sentiment_scores": [0.85, 0.05, 0.05, 0.05],
            "topic_label": 0,
            "topic_scores": [0.82] + [0.02] * 9,
        },
    })
    out_json = tmp_path / "out" / "report.json"
    out_md = tmp_path / "out" / "report.md"

    report = evaluate_review_signals(
        model_root=tmp_path / "models",
        profile_id="neu",
        validation_csv=raw_p,
        processed_validation_csv=proc_p,
        policy_path=ROOT / "services/review_policy.json",
        out_path=out_json,
        markdown_out_path=out_md,
        expected_raw_sha256=raw_sha,
        expected_processed_sha256=proc_sha,
        batch_size=2,
        registry=reg,
        command_str="pytest synthetic partial failure test",
    )

    # Batch size 2: batch 1 succeeds (2 items), batch 2 raises due to SECRET_GAMMA and falls back per-item (1 fails, 1 recovers)
    assert report["counts"] == {"total_rows": 4, "valid_count": 3, "failed_count": 1}
    assert report["policy"]["id"] == "review-signals-v1"
    assert report["policy"]["experimental"] is True
    assert report["policy_tuned"] is False
    assert "epoch" in report["disclaimer"].lower()
    assert report["metrics"]["sentiment"]["flagged_count"] == 1
    assert report["truncation"]["truncated_count"] == 1

    json_text = out_json.read_text(encoding="utf-8")
    md_text = out_md.read_text(encoding="utf-8")
    for secret in secret_phrases:
        assert secret not in json_text
        assert secret not in md_text
    assert "OOF" not in json_text


def test_identity_change_between_batches_aborts_without_writing_report(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    raw_p, proc_p, raw_sha, proc_sha = _write_csv_pair(
        tmp_path,
        [("Câu một", "0", "0"), ("Câu hai", "1", "1"), ("Câu ba", "2", "2")],
    )

    def flip_version(registry, _items):
        if len(registry.calls) == 1:
            # Swap model identity right after batch 1
            registry.model_version = "v2-swapped"

    reg = _ControlledEvalRegistry(on_predict=flip_version)
    out_json = tmp_path / "must_not_exist.json"
    out_md = tmp_path / "must_not_exist.md"

    with pytest.raises(ModelIdentityChangedError):
        evaluate_review_signals(
            model_root=tmp_path / "models",
            profile_id="neu",
            validation_csv=raw_p,
            processed_validation_csv=proc_p,
            policy_path=ROOT / "services/review_policy.json",
            out_path=out_json,
            markdown_out_path=out_md,
            expected_raw_sha256=raw_sha,
            expected_processed_sha256=proc_sha,
            batch_size=2,
            registry=reg,
        )

    assert not out_json.exists()
    assert not out_md.exists()

    # CLI returns non-zero and writes no report when identity changes
    code = cli_main([
        "--model-root", str(tmp_path / "nonexistent-models"),
        "--profile", "neu",
        "--validation-csv", str(raw_p),
        "--processed-validation-csv", str(proc_p),
        "--expected-raw-sha256", raw_sha,
        "--expected-processed-sha256", proc_sha,
        "--out", str(out_json),
        "--markdown-out", str(out_md),
    ])
    assert code != 0
    assert not out_json.exists()
    assert not out_md.exists()


def test_synthetic_bundle_integration_and_manifest_swap_guard(synthetic_neu_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    src_root, _ = synthetic_neu_bundle
    model_root = tmp_path / "copied_models"
    shutil.copytree(src_root, model_root)

    raw_p, proc_p, raw_sha, proc_sha = _write_csv_pair(
        tmp_path,
        [
            ("môn học tốt", "1.0", "2.0"),
            ("cơ sở vật chất ổn", "1.0", "4.0"),
            ("môn học " * 80, "0.0", "2.0"),
        ],
    )
    out_json = tmp_path / "synthetic_report.json"
    out_md = tmp_path / "synthetic_report.md"

    code = cli_main([
        "--model-root", str(model_root),
        "--profile", "neu",
        "--validation-csv", str(raw_p),
        "--processed-validation-csv", str(proc_p),
        "--expected-raw-sha256", raw_sha,
        "--expected-processed-sha256", proc_sha,
        "--out", str(out_json),
        "--markdown-out", str(out_md),
        "--batch-size", "2",
    ])
    assert code == 0
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["counts"] == {"total_rows": 3, "valid_count": 3, "failed_count": 0}
    assert report["model"]["manifest_sha256"]
    assert report["model"]["checkpoint_sha256"]
    assert report["truncation"]["truncated_count"] == 1
    assert "môn học" not in out_json.read_text(encoding="utf-8")

    # Mutate current.json mid-run between batches using a subclassed registry wrapper
    pointer_path = model_root / "neu" / "current.json"
    original_version = json.loads(pointer_path.read_text(encoding="utf-8"))["version"]
    clone_version = original_version + "_clone"
    src_bundle = model_root / "neu" / "versions" / original_version
    clone_bundle = model_root / "neu" / "versions" / clone_version
    shutil.copytree(src_bundle, clone_bundle)
    clone_manifest = json.loads((clone_bundle / "manifest.json").read_text(encoding="utf-8"))
    clone_manifest["model_version"] = clone_version
    (clone_bundle / "manifest.json").write_text(json.dumps(clone_manifest), encoding="utf-8")

    class _SwappingRegistry(ModelRegistry):
        def __init__(self, root: Path):
            super().__init__(root)
            self._batch_calls = 0

        def predict(self, profile: str, items: list[dict]) -> list[dict]:
            result = super().predict(profile, items)
            self._batch_calls += 1
            if self._batch_calls == 1:
                pointer_path.write_text(json.dumps({"version": clone_version}), encoding="utf-8")
            return result

    bad_out = tmp_path / "aborted_report.json"
    with pytest.raises(ModelIdentityChangedError):
        evaluate_review_signals(
            model_root=model_root,
            profile_id="neu",
            validation_csv=raw_p,
            processed_validation_csv=proc_p,
            policy_path=ROOT / "services/review_policy.json",
            out_path=bad_out,
            expected_raw_sha256=raw_sha,
            expected_processed_sha256=proc_sha,
            batch_size=2,
            registry=_SwappingRegistry(model_root),
        )
    assert not bad_out.exists()
