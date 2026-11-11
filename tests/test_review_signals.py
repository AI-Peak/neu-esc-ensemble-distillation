"""Unit tests for review_policy.json schema validation and review_signals calculations (T03)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from services.review_signals import (
    DEFAULT_POLICY_PATH,
    evaluate_item_signals,
    evaluate_task_signal,
    load_policy,
    resolve_policy_metadata,
    review_relation,
)
from services.storage.db import profile_for


def _write_policy(tmp_path: Path, payload: object, name: str = "policy.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_policy_payload(
    *,
    policy_id: str = "review-signals-v1",
    experimental: bool = True,
    neu_s=(0.60, 0.15),
    neu_t=(0.60, 0.15),
    uit_s=(0.60, 0.15),
    uit_t=(0.60, 0.15),
) -> dict:
    return {
        "id": policy_id,
        "experimental": experimental,
        "schemas": {
            "neu-v1": {
                "sentiment": {"top1_min": neu_s[0], "margin_min": neu_s[1]},
                "topic": {"top1_min": neu_t[0], "margin_min": neu_t[1]},
            },
            "uit-v1": {
                "sentiment": {"top1_min": uit_s[0], "margin_min": uit_s[1]},
                "topic": {"top1_min": uit_t[0], "margin_min": uit_t[1]},
            },
        },
    }


def _make_pred(
    pred_id: str = "pred-1",
    *,
    schema_id: str = "neu-v1",
    sent_scores=None,
    sent_label: int | None = None,
    topic_scores=None,
    topic_label: int | None = None,
    truncated: bool = False,
) -> dict:
    if sent_scores is None:
        sent_scores = [0.85, 0.05, 0.05, 0.05] if schema_id == "neu-v1" else [0.85, 0.10, 0.05]
    if topic_scores is None:
        topic_scores = ([0.82] + [0.02] * 9) if schema_id == "neu-v1" else [0.85, 0.05, 0.05, 0.05]
    if sent_label is None:
        sent_label = 0
    if topic_label is None:
        topic_label = 0
    return {
        "id": pred_id,
        "run_id": "run-1",
        "schema_id": schema_id,
        "sentiment": {"label_id": sent_label, "scores": sent_scores},
        "topic": {"label_id": topic_label, "scores": topic_scores},
        "truncated": truncated,
    }


def test_default_policy_metadata_and_process_immutability():
    raw_bytes = DEFAULT_POLICY_PATH.read_bytes()
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()

    first = load_policy()
    assert first["id"] == "review-signals-v1"
    assert first["experimental"] is True
    assert first["hash"] == expected_hash
    assert set(first["schemas"]) == {"neu-v1", "uit-v1"}
    for schema_id in ("neu-v1", "uit-v1"):
        for task in ("sentiment", "topic"):
            assert first["schemas"][schema_id][task] == {"top1_min": 0.60, "margin_min": 0.15}

    # Mutating caller copy must never leak into process-cached policy.
    first["id"] = "tampered"
    first["schemas"]["neu-v1"]["sentiment"]["top1_min"] = 0.99

    second = load_policy()
    assert second["id"] == "review-signals-v1"
    assert second["hash"] == expected_hash
    assert second["schemas"]["neu-v1"]["sentiment"]["top1_min"] == 0.60

    neu_meta = resolve_policy_metadata("neu-v1")
    uit_meta = resolve_policy_metadata("uit-v1")
    assert neu_meta == {
        "id": "review-signals-v1",
        "hash": expected_hash,
        "experimental": True,
        "schema_id": "neu-v1",
        "sentiment": {"top1_min": 0.60, "margin_min": 0.15},
        "topic": {"top1_min": 0.60, "margin_min": 0.15},
    }
    assert uit_meta["schema_id"] == "uit-v1"
    assert uit_meta["hash"] == expected_hash

    with pytest.raises(ValueError):
        resolve_policy_metadata("unknown-v9")


def test_strict_policy_validation_rejects_malformed_configs_without_fallback(tmp_path):
    # Extra top-level key
    bad_extra = _valid_policy_payload()
    bad_extra["extra"] = 123
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, bad_extra, "extra.json"))

    # Empty id / non-bool experimental / missing schema
    bad_id = _valid_policy_payload(policy_id="   ")
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, bad_id, "bad_id.json"))

    bad_exp = _valid_policy_payload()
    bad_exp["experimental"] = "true"
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, bad_exp, "bad_exp.json"))

    missing_schema = _valid_policy_payload()
    del missing_schema["schemas"]["uit-v1"]
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, missing_schema, "missing_schema.json"))

    missing_task = _valid_policy_payload()
    del missing_task["schemas"]["neu-v1"]["topic"]
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, missing_task, "missing_task.json"))

    # Invalid thresholds: bool, <0, >1, extra key
    bool_thresh = _valid_policy_payload(neu_s=(True, 0.15))
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, bool_thresh, "bool_thresh.json"))

    neg_thresh = _valid_policy_payload(neu_s=(-0.01, 0.15))
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, neg_thresh, "neg_thresh.json"))

    gt1_thresh = _valid_policy_payload(uit_t=(0.60, 1.01))
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, gt1_thresh, "gt1_thresh.json"))

    extra_thresh_key = _valid_policy_payload()
    extra_thresh_key["schemas"]["neu-v1"]["sentiment"]["extra"] = 0.5
    with pytest.raises(ValueError):
        load_policy(_write_policy(tmp_path, extra_thresh_key, "extra_thresh.json"))

    # Non-finite JSON constants (NaN / Infinity) & invalid UTF-8
    nan_path = tmp_path / "nan.json"
    nan_path.write_text(
        '{"id":"x","experimental":true,"schemas":{"neu-v1":{"sentiment":{"top1_min":NaN,"margin_min":0.15},"topic":{"top1_min":0.6,"margin_min":0.15}},"uit-v1":{"sentiment":{"top1_min":0.6,"margin_min":0.15},"topic":{"top1_min":0.6,"margin_min":0.15}}}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_policy(nan_path)

    bad_utf8 = tmp_path / "bad_utf8.json"
    bad_utf8.write_bytes(b"\xff\xfe{}")
    with pytest.raises(ValueError):
        load_policy(bad_utf8)


def test_strict_threshold_boundaries_without_rounding(tmp_path):
    neu = profile_for("neu")

    # Exact default threshold boundary: top1 == 0.60 -> clear (no rounding)
    sig_exact_top1 = evaluate_task_signal(
        _make_pred(sent_scores=[0.25, 0.15, 0.60, 0.0], sent_label=2),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert sig_exact_top1["state"] == "clear"
    assert sig_exact_top1["reasons"] == []
    assert sig_exact_top1["top1_label_id"] == 2
    assert sig_exact_top1["top2_label_id"] == 0
    assert sig_exact_top1["top1"] == pytest.approx(0.60)
    assert sig_exact_top1["margin"] == pytest.approx(0.35)

    # Just below 0.60 (even though 0.5999 rounds to 0.600 at 3 decimals) -> LOW_TOP1
    sig_below_top1 = evaluate_task_signal(
        _make_pred(sent_scores=[0.25, 0.1501, 0.5999, 0.0], sent_label=2),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert sig_below_top1["state"] == "flagged"
    assert sig_below_top1["reasons"] == ["LOW_TOP1"]

    # Exact binary float margin == 0.25 vs 0.249999 using explicit threshold margin_min=0.25
    # [0.625, 0.375, 0.0, 0.0] uses exact IEEE-754 binary fractions -> margin == 0.25 exactly
    sig_exact_margin = evaluate_task_signal(
        _make_pred(sent_scores=[0.625, 0.375, 0.0, 0.0], sent_label=0),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.625, "margin_min": 0.25},
    )
    assert sig_exact_margin["state"] == "clear"
    assert sig_exact_margin["reasons"] == []
    assert sig_exact_margin["margin"] == 0.25

    # Small margin ONLY (top1 >= 0.60, margin < 0.25) -> SMALL_MARGIN without LOW_TOP1
    sig_small_margin_only = evaluate_task_signal(
        _make_pred(sent_scores=[0.61, 0.39, 0.0, 0.0], sent_label=0),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.25},
    )
    assert sig_small_margin_only["state"] == "flagged"
    assert sig_small_margin_only["reasons"] == ["SMALL_MARGIN"]

    # Margin 0.1499 (rounds to 0.150) + LOW_TOP1 -> both reasons
    sig_both = evaluate_task_signal(
        _make_pred(sent_scores=[0.50, 0.3501, 0.1499, 0.0], sent_label=0),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert sig_both["state"] == "flagged"
    assert sig_both["reasons"] == ["LOW_TOP1", "SMALL_MARGIN"]

    # Custom policy via load_policy keeps schema-specific thresholds independent
    custom_policy = load_policy(
        _write_policy(
            tmp_path,
            _valid_policy_payload(
                policy_id="custom-v2",
                neu_s=(0.90, 0.50),
                neu_t=(0.50, 0.10),
                uit_s=(0.55, 0.10),
                uit_t=(0.55, 0.10),
            ),
            "custom.json",
        )
    )
    item_sig = evaluate_item_signals(
        _make_pred(
            sent_scores=[0.80, 0.10, 0.05, 0.05],
            sent_label=0,
            topic_scores=[0.65] + [0.05] * 7 + [0.0, 0.0],
            topic_label=0,
        ),
        {},
        neu,
        policy=custom_policy,
    )
    assert item_sig["policy_id"] == "custom-v2"
    assert item_sig["sentiment"]["state"] == "flagged" and item_sig["sentiment"]["reasons"] == ["LOW_TOP1"]
    assert item_sig["topic"]["state"] == "clear" and item_sig["topic"]["reasons"] == []


def test_tie_breaking_uses_ascending_label_id():
    neu = profile_for("neu")
    uit = profile_for("uit")

    # NEU sentiment tie between label 1 (0.45) and label 3 (0.45) -> top1=1, top2=3, margin=0
    sig_sent = evaluate_task_signal(
        _make_pred(sent_scores=[0.05, 0.45, 0.05, 0.45], sent_label=1),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert sig_sent["top1_label_id"] == 1
    assert sig_sent["top2_label_id"] == 3
    assert sig_sent["margin"] == 0.0
    assert sig_sent["reasons"] == ["LOW_TOP1", "SMALL_MARGIN"]

    # NEU topic tie between label 3 (0.35) and label 7 (0.35) -> top1=3, top2=7
    t_scores = [0.05, 0.05, 0.05, 0.35, 0.05, 0.05, 0.0, 0.35, 0.05, 0.0]
    sig_topic = evaluate_task_signal(
        _make_pred(topic_scores=t_scores, topic_label=3),
        None,
        neu,
        "topic",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert sig_topic["top1_label_id"] == 3
    assert sig_topic["top2_label_id"] == 7
    assert sig_topic["margin"] == 0.0

    # Three-way tie on UIT sentiment [0.3334, 0.3333, 0.3333] vs exact tie [0.5, 0.5, 0.0]
    sig_uit = evaluate_task_signal(
        _make_pred(
            schema_id="uit-v1",
            sent_scores=[0.5, 0.5, 0.0],
            sent_label=0,
            topic_scores=[0.85, 0.05, 0.05, 0.05],
            topic_label=0,
        ),
        None,
        uit,
        "sentiment",
        {"top1_min": 0.50, "margin_min": 0.10},
    )
    assert sig_uit["top1_label_id"] == 0
    assert sig_uit["top2_label_id"] == 1
    assert sig_uit["margin"] == 0.0
    assert sig_uit["reasons"] == ["SMALL_MARGIN"]


def test_missing_prediction_and_malformed_scores_unavailable():
    neu = profile_for("neu")

    # Missing prediction -> NO_PREDICTION, truncated=None, pending=False
    no_pred = evaluate_item_signals(None, {}, neu)
    assert no_pred["prediction_id"] is None
    assert no_pred["truncated"] is None
    assert no_pred["pending_signal_review"] is False
    for task in ("sentiment", "topic"):
        assert no_pred[task]["state"] == "unavailable"
        assert no_pred[task]["reasons"] == ["NO_PREDICTION"]
        assert no_pred[task]["top1"] is None
        assert no_pred[task]["top2"] is None
        assert no_pred[task]["margin"] is None
        assert no_pred[task]["top1_label_id"] is None
        assert no_pred[task]["top2_label_id"] is None
        assert no_pred[task]["review_relation"] == "unreviewed"

    bad_score_cases = [
        [0.5, 0.3, 0.2],  # wrong length (3 instead of 4)
        [0.4, 0.4, 0.2, 0.0, 0.0],  # too long
        [float("nan"), 0.5, 0.3, 0.2],  # NaN
        [float("inf"), 0.0, 0.0, 0.0],  # Inf
        [True, 0.0, 0.0, 0.0],  # bool treated as invalid score
        [-0.01, 0.51, 0.30, 0.20],  # < 0
        [1.01, 0.0, 0.0, 0.0],  # > 1
        [0.50, 0.20, 0.20, 0.098],  # sum = 0.998 (off by > 0.001)
        [0.50, 0.20, 0.20, 0.102],  # sum = 1.002 (off by > 0.001)
        "not-a-list",
    ]
    for bad_scores in bad_score_cases:
        pred = _make_pred(sent_scores=bad_scores, sent_label=0)
        res = evaluate_item_signals(pred, {}, neu)
        assert res["sentiment"]["state"] == "unavailable"
        assert res["sentiment"]["reasons"] == ["INVALID_SCORES"]
        assert res["sentiment"]["top1"] is None
        assert res["sentiment"]["margin"] is None
        # Healthy topic task remains independent and clear
        assert res["topic"]["state"] == "clear"
        assert res["topic"]["reasons"] == []
        assert res["pending_signal_review"] is False

    # Sum within 0.001 tolerance (1.0005) must still succeed
    near_one = evaluate_task_signal(
        _make_pred(sent_scores=[0.8005, 0.10, 0.05, 0.05], sent_label=0),
        None,
        neu,
        "sentiment",
        {"top1_min": 0.60, "margin_min": 0.15},
    )
    assert near_one["state"] == "clear"

    # Invalid schema_id or invalid label_id triggers INVALID_SCORES
    wrong_schema = _make_pred(schema_id="uit-v1")
    sig_wrong_schema = evaluate_item_signals(wrong_schema, {}, neu)
    assert sig_wrong_schema["sentiment"]["state"] == "unavailable"
    assert sig_wrong_schema["sentiment"]["reasons"] == ["INVALID_SCORES"]


def test_review_relation_and_pending_signal_review_truth_table():
    neu = profile_for("neu")

    # review_relation helper unit cases
    assert review_relation(None, "p1") == "unreviewed"
    assert review_relation({"status": "unreviewed", "source_prediction_id": "p1"}, "p1") == "unreviewed"
    assert review_relation({"status": "confirmed", "source_prediction_id": "p1"}, "p1") == "current_prediction"
    assert review_relation({"status": "corrected", "source_prediction_id": "p1"}, "p1") == "current_prediction"
    assert review_relation({"status": "corrected", "source_prediction_id": None}, "p1") == "manual"
    assert review_relation({"status": "corrected", "source_prediction_id": None}, None) == "manual"
    assert review_relation({"status": "confirmed", "source_prediction_id": "p-old"}, "p1") == "other_prediction"
    assert review_relation({"status": "confirmed", "source_prediction_id": "p-old"}, None) == "other_prediction"

    # Case 1: sentiment flagged, topic clear, neither reviewed -> pending=True
    s_flag_pred = _make_pred(
        pred_id="p1",
        sent_scores=[0.50, 0.30, 0.10, 0.10],
        sent_label=0,
        topic_scores=[0.82] + [0.02] * 9,
        topic_label=0,
        truncated=False,
    )
    r1 = evaluate_item_signals(s_flag_pred, {}, neu)
    assert r1["sentiment"]["state"] == "flagged"
    assert r1["topic"]["state"] == "clear"
    assert r1["pending_signal_review"] is True

    # Reviewing ONLY topic leaves flagged sentiment unaddressed -> pending=True
    r2 = evaluate_item_signals(
        s_flag_pred,
        {"topic": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p1"}},
        neu,
    )
    assert r2["topic"]["review_relation"] == "current_prediction"
    assert r2["sentiment"]["review_relation"] == "unreviewed"
    assert r2["pending_signal_review"] is True

    # Reviewing flagged sentiment against current prediction clears pending even if clear topic is unreviewed
    r3 = evaluate_item_signals(
        s_flag_pred,
        {"sentiment": {"status": "corrected", "label_id": 2, "source_prediction_id": "p1"}},
        neu,
    )
    assert r3["sentiment"]["review_relation"] == "current_prediction"
    assert r3["pending_signal_review"] is False
    # Scores & reasons do NOT disappear after review
    assert r3["sentiment"]["state"] == "flagged"
    assert r3["sentiment"]["reasons"] == ["LOW_TOP1"]

    # Manual review (source_prediction_id=None) also clears pending
    r4 = evaluate_item_signals(
        s_flag_pred,
        {"sentiment": {"status": "corrected", "label_id": 1, "source_prediction_id": None}},
        neu,
    )
    assert r4["sentiment"]["review_relation"] == "manual"
    assert r4["pending_signal_review"] is False

    # Review attached to OTHER prediction does NOT clear pending
    r5 = evaluate_item_signals(
        s_flag_pred,
        {"sentiment": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p-old"}},
        neu,
    )
    assert r5["sentiment"]["review_relation"] == "other_prediction"
    assert r5["pending_signal_review"] is True

    # Case 2: Both tasks clear in scores, truncated=True -> requires BOTH tasks addressed
    trunc_clear_pred = _make_pred(pred_id="p2", truncated=True)
    t1 = evaluate_item_signals(trunc_clear_pred, {}, neu)
    assert t1["sentiment"]["state"] == "clear" and t1["topic"]["state"] == "clear"
    assert t1["truncated"] is True
    assert t1["pending_signal_review"] is True

    # Only sentiment addressed -> still pending because truncated requires both tasks addressed
    t2 = evaluate_item_signals(
        trunc_clear_pred,
        {"sentiment": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p2"}},
        neu,
    )
    assert t2["pending_signal_review"] is True

    # Sentiment current_prediction + topic manual -> both addressed -> pending=False
    t3 = evaluate_item_signals(
        trunc_clear_pred,
        {
            "sentiment": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p2"},
            "topic": {"status": "corrected", "label_id": 2, "source_prediction_id": None},
        },
        neu,
    )
    assert t3["pending_signal_review"] is False

    # If one is other_prediction while truncated=True -> pending=True
    t4 = evaluate_item_signals(
        trunc_clear_pred,
        {
            "sentiment": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p2"},
            "topic": {"status": "confirmed", "label_id": 0, "source_prediction_id": "p-old"},
        },
        neu,
    )
    assert t4["pending_signal_review"] is True
