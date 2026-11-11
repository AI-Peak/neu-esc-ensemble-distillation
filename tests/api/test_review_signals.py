"""API, filter parity, review provenance, and export snapshot tests for T03."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from services.api.main import create_app
import services.review_signals as review_signals_mod
from services.review_signals import DEFAULT_POLICY_PATH, load_policy
from services.storage.db import profile_for
from services.worker import Worker

EXPECTED_CSV_COLUMNS = [
    "item_id", "source_row", "text", "metadata", "revision_id", "revision", "schema_id",
    "selected_run_id", "prediction_status", "prediction_id", "run_id", "model_id", "model_version",
    "label_source", "selected_sentiment", "selected_topic", "ai_sentiment", "ai_topic",
    "sentiment_scores", "topic_scores", "reference_sentiment", "reference_sentiment_source",
    "reference_topic", "reference_topic_source", "review_sentiment", "review_sentiment_status",
    "review_sentiment_revision", "review_sentiment_note", "review_sentiment_source_prediction_id",
    "review_topic", "review_topic_status", "review_topic_revision", "review_topic_note",
    "review_topic_source_prediction_id", "effective_sentiment", "effective_topic",
    "token_count_before_truncation", "truncated", "warnings", "error",
]


class ControlledSignalRegistry:
    """Deterministic software test double with explicit score vectors per text."""

    __test__ = False

    def __init__(self, specs=None, *, fail_texts=None, version="v1"):
        self.available = True
        self.version = version
        self.specs = dict(specs or {})
        self.fail_texts = set(fail_texts or ())
        self.calls = []

    def status(self, profile):
        return {
            "available": self.available,
            "reason": None if self.available else "Artifact missing",
            "model_id": f"test-double-{profile}",
            "model_version": self.version,
            "schema_id": profile_for(profile)["schema_id"],
        }

    def predict(self, profile, items):
        self.calls.append([i["item_id"] for i in items])
        prof = profile_for(profile)
        outputs = []
        for item in items:
            if item["text"] in self.fail_texts:
                raise RuntimeError("PRIVATE TEXT SHOULD NEVER LEAK")
            spec = self.specs.get(item["text"], {})
            s_count = len(prof["sentiment"])
            t_count = len(prof["topic"])
            default_s = [0.85] + [round(0.15 / (s_count - 1), 6)] * (s_count - 1)
            default_t = [0.82] + [round(0.18 / (t_count - 1), 6)] * (t_count - 1)
            s_scores = list(spec.get("sentiment_scores", default_s))
            t_scores = list(spec.get("topic_scores", default_t))
            s_label = spec.get("sentiment_label", s_scores.index(max(s_scores)))
            t_label = spec.get("topic_label", t_scores.index(max(t_scores)))
            truncated = bool(spec.get("truncated", False))
            outputs.append({
                "item_id": item["item_id"],
                "revision_id": item["revision_id"],
                "model_id": f"test-double-{profile}",
                "model_version": self.version,
                "schema_id": prof["schema_id"],
                "sentiment": {"label_id": s_label, "scores": s_scores},
                "topic": {"label_id": t_label, "scores": t_scores},
                "token_count_before_truncation": 140 if truncated else 10,
                "truncated": truncated,
                "warnings": ["INPUT_TRUNCATED"] if truncated else [],
                "duration_ms": 1.0,
            })
        return list(reversed(outputs))


@pytest.fixture
def env(tmp_path):
    registry = ControlledSignalRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        yield client, app.state.store, registry, Worker(tmp_path, registry, batch_size=1)


def make_dataset(client, profile="neu", items=None, **kwargs):
    payload_items = items if items is not None else [dict(text="Câu một"), dict(text="Câu hai")]
    response = client.post(
        "/api/v1/datasets",
        json=dict(name="Signal test", profile=profile, items=payload_items, **kwargs),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_run(client, dataset):
    response = client.post("/api/v1/analysis-runs", json=dict(dataset_id=dataset["id"]))
    assert response.status_code == 202, response.text
    return response.json()


def drain(worker):
    for _ in range(510):
        if not worker.run_once():
            return
    raise AssertionError("Worker did not drain")


def _install_custom_default_policy(monkeypatch, tmp_path: Path, payload: dict) -> dict:
    custom_path = tmp_path / "custom_review_policy.json"
    custom_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_policy(custom_path)
    monkeypatch.setattr(review_signals_mod, "DEFAULT_POLICY_PATH", custom_path)
    monkeypatch.setattr(review_signals_mod, "_DEFAULT_POLICY", loaded)
    return loaded


def test_review_policy_endpoint_matches_summary_and_items(env):
    c, _s, r, w = env
    expected_policy = load_policy(DEFAULT_POLICY_PATH)

    for prof in ("neu", "uit"):
        res = c.get("/api/v1/review-policy", params={"profile": prof})
        assert res.status_code == 200, res.text
        policy = res.json()
        assert policy["id"] == "review-signals-v1"
        assert policy["hash"] == expected_policy["hash"]
        assert policy["experimental"] is True
        assert policy["schema_id"] == f"{prof}-v1"
        assert policy["sentiment"] == {"top1_min": 0.60, "margin_min": 0.15}
        assert policy["topic"] == {"top1_min": 0.60, "margin_min": 0.15}

    bad_prof = c.get("/api/v1/review-policy", params={"profile": "unknown"})
    assert bad_prof.status_code == 422
    assert bad_prof.json()["code"] == "INVALID_PROFILE"

    missing_prof = c.get("/api/v1/review-policy")
    assert missing_prof.status_code == 422

    # Summary review_policy and item review_signals share exact same policy metadata
    d = make_dataset(c, profile="neu", items=[dict(text="Kiểm tra policy")])
    create_run(c, d)
    drain(w)

    summary = c.get(f"/api/v1/datasets/{d['id']}/summary").json()
    assert summary["review_policy"] == c.get("/api/v1/review-policy", params={"profile": "neu"}).json()

    items_res = c.get(f"/api/v1/datasets/{d['id']}/items").json()
    sig = items_res["items"][0]["review_signals"]
    assert sig["policy_id"] == summary["review_policy"]["id"]
    assert sig["policy_hash"] == summary["review_policy"]["hash"]
    assert sig["experimental"] is True

    # Invalid filter enums/types rejected cleanly with 422 INVALID_FILTER across items, summary, and exports
    for method, url, kwargs in (
        ("get", f"/api/v1/datasets/{d['id']}/items", {"params": {"review_signal": "bogus"}}),
        ("get", f"/api/v1/datasets/{d['id']}/summary", {"params": {"review_signal": "bogus"}}),
        ("post", f"/api/v1/datasets/{d['id']}/exports", {"json": {"review_signal": "bogus"}}),
        ("post", f"/api/v1/datasets/{d['id']}/exports", {"json": {"scope": "all", "review_signal": "bogus"}}),
        ("post", f"/api/v1/datasets/{d['id']}/exports", {"json": {"review_status": "bogus"}}),
        ("post", f"/api/v1/datasets/{d['id']}/exports", {"json": {"sentiment": "not-an-int"}}),
    ):
        resp = getattr(c, method)(url, **kwargs)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "INVALID_FILTER"

    # Non-filter export schema errors (invalid scope, extra fields, non-dict / broken JSON) stay 422 VALIDATION_ERROR
    for kwargs in (
        {"json": {"scope": "bogus"}},
        {"json": {"unexpected_extra": 1}},
        {"json": ["not-a-dict"]},
        {"content": "{broken-json", "headers": {"Content-Type": "application/json"}},
    ):
        resp = c.post(f"/api/v1/datasets/{d['id']}/exports", **kwargs)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "VALIDATION_ERROR"


def test_signal_filters_and_legacy_needs_review_unchanged(env, monkeypatch, tmp_path):
    c, _s, r, w = env
    clear_s = [0.85, 0.05, 0.05, 0.05]
    clear_t = [0.82] + [0.02] * 9

    r.specs = {
        "row-sent-low": {
            "sentiment_scores": [0.25, 0.15, 0.50, 0.10],  # top1=0.50 (label 2) < 0.60, margin=0.25 -> LOW_TOP1
            "topic_scores": clear_t,
        },
        "row-topic-tie": {
            "sentiment_scores": clear_s,
            "topic_scores": [0.05, 0.40, 0.05, 0.05, 0.40, 0.05, 0.0, 0.0, 0.0, 0.0],  # tie 1 & 4 -> margin 0
        },
        "row-both-clear-reviewed": {
            "sentiment_scores": clear_s,
            "topic_scores": clear_t,
        },
        "row-trunc-clear": {
            "sentiment_scores": clear_s,
            "topic_scores": clear_t,
            "truncated": True,
        },
        "row-reviewed-low-top1": {
            "sentiment_scores": [0.55, 0.25, 0.10, 0.10],  # top1=0.55 < 0.60
            "topic_scores": clear_t,
        },
        "row-trunc-reviewed-one": {
            "sentiment_scores": clear_s,
            "topic_scores": clear_t,
            "truncated": True,
        },
        "row-failed": {
            "sentiment_scores": clear_s,
            "topic_scores": clear_t,
        },
    }
    r.fail_texts.add("row-failed")

    texts = [
        "row-sent-low",
        "row-topic-tie",
        "row-both-clear-reviewed",
        "row-trunc-clear",
        "row-reviewed-low-top1",
        "row-trunc-reviewed-one",
        "row-failed",
    ]
    d = make_dataset(c, profile="neu", items=[dict(text=t) for t in texts])
    create_run(c, d)
    drain(w)

    all_rows = {item["text"]: item for item in c.get(f"/api/v1/datasets/{d['id']}/items", params={"page_size": 50}).json()["items"]}

    # Review row-both-clear-reviewed completely
    for task, lid in (("sentiment", 0), ("topic", 0)):
        item = all_rows["row-both-clear-reviewed"]
        assert c.put(
            f"/api/v1/items/{item['id']}/review",
            json=dict(
                task=task,
                status="confirmed",
                label_id=lid,
                expected_revision=1,
                expected_review_revision=0,
                source_prediction_id=item["prediction"]["id"],
            ),
        ).status_code == 200

    # Review row-reviewed-low-top1 completely against current prediction
    for task, lid in (("sentiment", 0), ("topic", 0)):
        item = all_rows["row-reviewed-low-top1"]
        assert c.put(
            f"/api/v1/items/{item['id']}/review",
            json=dict(
                task=task,
                status="confirmed",
                label_id=lid,
                expected_revision=1,
                expected_review_revision=0,
                source_prediction_id=item["prediction"]["id"],
            ),
        ).status_code == 200

    # Review ONLY sentiment on row-trunc-reviewed-one
    item_trunc_one = all_rows["row-trunc-reviewed-one"]
    assert c.put(
        f"/api/v1/items/{item_trunc_one['id']}/review",
        json=dict(
            task="sentiment",
            status="confirmed",
            label_id=0,
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=item_trunc_one["prediction"]["id"],
        ),
    ).status_code == 200

    def texts_for(**params):
        return {
            item["text"]
            for item in c.get(f"/api/v1/datasets/{d['id']}/items", params=params).json()["items"]
        }

    # Tie breaking check on row-topic-tie
    tie_detail = c.get(f"/api/v1/items/{all_rows['row-topic-tie']['id']}").json()
    assert tie_detail["review_signals"]["topic"]["top1_label_id"] == 1
    assert tie_detail["review_signals"]["topic"]["top2_label_id"] == 4
    assert tie_detail["review_signals"]["topic"]["margin"] == 0.0
    assert tie_detail["review_signals"]["topic"]["reasons"] == ["LOW_TOP1", "SMALL_MARGIN"]

    # Check filter buckets
    assert texts_for(review_signal="all") == set(texts)
    assert texts_for(review_signal="model_uncertain") == {
        "row-sent-low",
        "row-topic-tie",
        "row-reviewed-low-top1",
    }
    assert texts_for(review_signal="sentiment_uncertain") == {
        "row-sent-low",
        "row-reviewed-low-top1",
    }
    assert texts_for(review_signal="topic_uncertain") == {"row-topic-tie"}
    assert texts_for(review_signal="truncated") == {
        "row-trunc-clear",
        "row-trunc-reviewed-one",
    }
    assert texts_for(review_signal="pending_signal_review") == {
        "row-sent-low",
        "row-topic-tie",
        "row-trunc-clear",
        "row-trunc-reviewed-one",
    }

    # Legacy needs_review keeps exact legacy semantics (includes reviewed item with max(scores)<0.6, error, trunc)
    assert texts_for(review_status="needs_review") == {
        "row-sent-low",
        "row-topic-tie",
        "row-trunc-clear",
        "row-reviewed-low-top1",
        "row-trunc-reviewed-one",
        "row-failed",
    }

    # Complete topic review on row-trunc-reviewed-one -> leaves pending_signal_review, stays in truncated
    assert c.put(
        f"/api/v1/items/{item_trunc_one['id']}/review",
        json=dict(
            task="topic",
            status="corrected",
            label_id=5,
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=None,
        ),
    ).status_code == 200
    assert "row-trunc-reviewed-one" not in texts_for(review_signal="pending_signal_review")
    assert "row-trunc-reviewed-one" in texts_for(review_signal="truncated")

    # Verify SMALL_MARGIN-only (with top1 >= 0.60) via temporary custom policy does NOT trigger legacy needs_review
    r2 = ControlledSignalRegistry(specs={
        "margin-only-reviewed": {
            "sentiment_scores": [0.61, 0.39, 0.0, 0.0],  # top1=0.61 >= 0.60, margin=0.22
            "topic_scores": clear_t,
        }
    })
    with TestClient(create_app(tmp_path / "custom_rt", r2)) as c2:
        w2 = Worker(tmp_path / "custom_rt", r2, batch_size=1)
        d2 = make_dataset(c2, profile="neu", items=[dict(text="margin-only-reviewed")])
        create_run(c2, d2)
        drain(w2)
        item2 = c2.get(f"/api/v1/datasets/{d2['id']}/items").json()["items"][0]
        for task, lid in (("sentiment", 0), ("topic", 0)):
            assert c2.put(
                f"/api/v1/items/{item2['id']}/review",
                json=dict(
                    task=task,
                    status="confirmed",
                    label_id=lid,
                    expected_revision=1,
                    expected_review_revision=0,
                    source_prediction_id=item2["prediction"]["id"],
                ),
            ).status_code == 200

        _install_custom_default_policy(monkeypatch, tmp_path, {
            "id": "custom-margin-test",
            "experimental": True,
            "schemas": {
                "neu-v1": {
                    "sentiment": {"top1_min": 0.60, "margin_min": 0.25},
                    "topic": {"top1_min": 0.60, "margin_min": 0.15},
                },
                "uit-v1": {
                    "sentiment": {"top1_min": 0.60, "margin_min": 0.15},
                    "topic": {"top1_min": 0.60, "margin_min": 0.15},
                },
            },
        })
        assert len(c2.get(f"/api/v1/datasets/{d2['id']}/items", params={"review_signal": "sentiment_uncertain"}).json()["items"]) == 1
        assert len(c2.get(f"/api/v1/datasets/{d2['id']}/items", params={"review_status": "needs_review"}).json()["items"]) == 0


def test_review_lifecycle_provenance_run_change_text_edit_reference_and_malformed_db(env):
    c, store, r, w = env
    clear_t = [0.82] + [0.02] * 9
    r.specs = {
        "flag-item": {
            "sentiment_scores": [0.48, 0.37, 0.10, 0.05],  # LOW_TOP1 + SMALL_MARGIN
            "topic_scores": clear_t,
        },
        "manual-survives-run": {
            "sentiment_scores": [0.48, 0.37, 0.10, 0.05],
            "topic_scores": clear_t,
        },
        "ref-only": {
            "sentiment_scores": [0.48, 0.37, 0.10, 0.05],
            "topic_scores": clear_t,
        },
    }

    # Import ref-only via CSV preview with reference labels
    csv_bytes = "text,ref_s,ref_t\nref-only,2,4\n".encode("utf-8")
    prev = c.post("/api/v1/imports/preview", files={"file": ("ref.csv", csv_bytes, "text/csv")}).json()
    d_ref = c.post(
        "/api/v1/datasets",
        json=dict(
            name="Ref check",
            profile="neu",
            preview_id=prev["preview_id"],
            text_column="text",
            reference=dict(source="Chú thích mẫu", sentiment_column="ref_s", topic_column="ref_t"),
        ),
    ).json()
    create_run(c, d_ref)
    drain(w)
    ref_item = c.get(f"/api/v1/datasets/{d_ref['id']}/items").json()["items"][0]
    assert ref_item["reference"]["sentiment"]["label_id"] == 2
    assert ref_item["review_signals"]["sentiment"]["review_relation"] == "unreviewed"
    assert ref_item["review_signals"]["pending_signal_review"] is True

    # Main lifecycle dataset
    d = make_dataset(c, profile="neu", items=[dict(text="flag-item"), dict(text="manual-survives-run")])
    run1 = create_run(c, d)
    drain(w)
    rows = {i["text"]: i for i in c.get(f"/api/v1/datasets/{d['id']}/items").json()["items"]}
    flag_item = rows["flag-item"]
    manual_item = rows["manual-survives-run"]
    pred1_id = flag_item["prediction"]["id"]
    orig_signals_num = {
        k: flag_item["review_signals"]["sentiment"][k]
        for k in ("state", "top1_label_id", "top2_label_id", "top1", "top2", "margin", "reasons")
    }

    # Confirm sentiment against run 1 prediction
    rev1 = c.put(
        f"/api/v1/items/{flag_item['id']}/review",
        json=dict(
            task="sentiment",
            status="confirmed",
            label_id=0,
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=pred1_id,
        ),
    ).json()
    assert rev1["revision"] == 1
    after_confirm = c.get(f"/api/v1/items/{flag_item['id']}").json()
    for k, v in orig_signals_num.items():
        assert after_confirm["review_signals"]["sentiment"][k] == v
    assert after_confirm["prediction"] == flag_item["prediction"]
    assert after_confirm["review_signals"]["sentiment"]["review_relation"] == "current_prediction"
    assert after_confirm["review_signals"]["pending_signal_review"] is False

    # Signals must be identical under label_source=ai vs effective
    eff_list = c.get(f"/api/v1/datasets/{d['id']}/items", params={"label_source": "effective"}).json()["items"]
    ai_list = c.get(f"/api/v1/datasets/{d['id']}/items", params={"label_source": "ai"}).json()["items"]
    assert [i["review_signals"] for i in eff_list] == [i["review_signals"] for i in ai_list]

    # Correct manually (source_prediction_id=None) -> relation='manual'
    rev2 = c.put(
        f"/api/v1/items/{flag_item['id']}/review",
        json=dict(
            task="sentiment",
            status="corrected",
            label_id=2,
            note="Sửa tay",
            expected_revision=1,
            expected_review_revision=1,
            source_prediction_id=None,
        ),
    ).json()
    assert rev2["revision"] == 2
    after_manual = c.get(f"/api/v1/items/{flag_item['id']}").json()
    assert after_manual["effective"]["sentiment"] == 2
    assert after_manual["review_signals"]["sentiment"]["review_relation"] == "manual"
    assert after_manual["review_signals"]["pending_signal_review"] is False

    # Unreview -> relation='unreviewed', pending returns True
    rev3 = c.put(
        f"/api/v1/items/{flag_item['id']}/review",
        json=dict(
            task="sentiment",
            status="unreviewed",
            expected_revision=1,
            expected_review_revision=2,
        ),
    ).json()
    assert rev3["revision"] == 3
    after_unrev = c.get(f"/api/v1/items/{flag_item['id']}").json()
    assert after_unrev["review_signals"]["sentiment"]["review_relation"] == "unreviewed"
    assert after_unrev["review_signals"]["pending_signal_review"] is True

    # Restore rev1 (current_prediction) -> relation='current_prediction', pending=False
    restored = c.post(
        f"/api/v1/items/{flag_item['id']}/reviews/restore",
        json=dict(task="sentiment", review_revision=1, expected_revision=1, expected_review_revision=3),
    ).json()
    assert restored["revision"] == 4
    after_restore = c.get(f"/api/v1/items/{flag_item['id']}").json()
    assert after_restore["review_signals"]["sentiment"]["review_relation"] == "current_prediction"
    assert after_restore["review_signals"]["pending_signal_review"] is False

    # Set manual review on second item so we can compare across run2
    assert c.put(
        f"/api/v1/items/{manual_item['id']}/review",
        json=dict(
            task="sentiment",
            status="corrected",
            label_id=2,
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=None,
        ),
    ).status_code == 200

    # Run 2 with model v2 & flagged scores
    r.version = "v2"
    r.specs["flag-item"]["sentiment_scores"] = [0.52, 0.38, 0.05, 0.05]
    run2 = create_run(c, d)
    drain(w)

    # Current view (run 2): flag_item review is linked to pred1 -> other_prediction -> pending becomes True!
    latest_flag = c.get(f"/api/v1/items/{flag_item['id']}").json()
    assert latest_flag["prediction"]["run_id"] == run2["id"]
    assert latest_flag["effective"]["sentiment"] == 0  # effective still uses human review
    assert latest_flag["review_signals"]["sentiment"]["review_relation"] == "other_prediction"
    assert latest_flag["review_signals"]["sentiment"]["top1"] == pytest.approx(0.52)
    assert latest_flag["review_signals"]["pending_signal_review"] is True

    # Manual review (source_prediction_id=None) stays 'manual' even in run 2!
    latest_manual = c.get(f"/api/v1/items/{manual_item['id']}").json()
    assert latest_manual["review_signals"]["sentiment"]["review_relation"] == "manual"
    assert latest_manual["review_signals"]["pending_signal_review"] is False

    # Historical run 1 view keeps run 1 prediction, scores, and current_prediction relation
    hist_flag = c.get(f"/api/v1/items/{flag_item['id']}", params={"run_id": run1["id"]}).json()
    assert hist_flag["prediction"]["id"] == pred1_id
    assert hist_flag["review_signals"]["sentiment"]["top1"] == pytest.approx(0.48)
    assert hist_flag["review_signals"]["sentiment"]["review_relation"] == "current_prediction"
    assert hist_flag["review_signals"]["pending_signal_review"] is False

    # Edit text -> creates revision 2 with NO_PREDICTION, unreviewed, truncated=None, pending=False
    edited = c.patch(
        f"/api/v1/items/{flag_item['id']}/text",
        json=dict(text="Nội dung đã chỉnh sửa", expected_revision=1),
    ).json()
    assert edited["revision"] == 2
    assert edited["review_signals"]["prediction_id"] is None
    assert edited["review_signals"]["truncated"] is None
    assert edited["review_signals"]["pending_signal_review"] is False
    assert edited["review_signals"]["sentiment"]["state"] == "unavailable"
    assert edited["review_signals"]["sentiment"]["reasons"] == ["NO_PREDICTION"]
    assert edited["review_signals"]["sentiment"]["review_relation"] == "unreviewed"

    # Historical view for run 1 still resolves revision 1 cleanly
    hist_after_edit = c.get(f"/api/v1/items/{flag_item['id']}", params={"run_id": run1["id"]}).json()
    assert hist_after_edit["stale"] is True
    assert hist_after_edit["review_signals"]["sentiment"]["state"] == "flagged"

    # Corrupt stored prediction payload directly in SQLite -> backend surfaces INVALID_SCORES cleanly (200)
    with store.tx() as db:
        row = db.execute("SELECT id, payload FROM predictions WHERE item_id=? AND run_id=?", (manual_item["id"], run2["id"])).fetchone()
        bad_payload = json.loads(row["payload"])
        bad_payload["sentiment"]["scores"] = [0.5, 0.5]  # wrong length (2 instead of 4)
        db.execute("UPDATE predictions SET payload=? WHERE id=?", (json.dumps(bad_payload), row["id"]))
    corrupt_item = c.get(f"/api/v1/items/{manual_item['id']}").json()
    assert corrupt_item["review_signals"]["sentiment"]["state"] == "unavailable"
    assert corrupt_item["review_signals"]["sentiment"]["reasons"] == ["INVALID_SCORES"]
    assert corrupt_item["review_signals"]["topic"]["state"] == "clear"


def test_and_filter_parity_and_scope_all_export(env):
    c, _s, r, w = env
    clear_s = [0.05, 0.85, 0.05, 0.05]  # Positive (1)
    neg_clear_s = [0.05, 0.05, 0.85, 0.05]  # Negative (2)
    neg_flag_s = [0.25, 0.15, 0.50, 0.10]  # Negative (2), LOW_TOP1
    clear_t4 = [0.02] * 4 + [0.82] + [0.02] * 5  # Service (4)
    flag_t4 = [0.02] * 4 + [0.50, 0.38] + [0.02] * 4  # Service (4), LOW_TOP1 + SMALL_MARGIN

    r.specs = {
        "alpha dịch vụ tệ low": {"sentiment_scores": neg_flag_s, "topic_scores": clear_t4},
        "alpha dịch vụ vừa flag topic": {"sentiment_scores": clear_s, "topic_scores": flag_t4, "truncated": True},
        "alpha dịch vụ tốt clear": {"sentiment_scores": neg_clear_s, "topic_scores": clear_t4, "truncated": True},
        "beta học tập flagged": {"sentiment_scores": neg_flag_s, "topic_scores": [0.02, 0.02, 0.82] + [0.02] * 7},
    }
    d = make_dataset(c, profile="neu", items=[dict(text=t) for t in r.specs])
    run1 = create_run(c, d)
    drain(w)

    # Confirm review on first item so it stays model_uncertain / sentiment_uncertain but leaves pending_signal_review
    items_all = c.get(f"/api/v1/datasets/{d['id']}/items").json()["items"]
    first = next(i for i in items_all if i["text"] == "alpha dịch vụ tệ low")
    assert c.put(
        f"/api/v1/items/{first['id']}/review",
        json=dict(
            task="sentiment",
            status="corrected",
            label_id=1,  # changed effective to Positive(1), AI remains Negative(2)
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=first["prediction"]["id"],
        ),
    ).status_code == 200

    # Legacy filter params without review_signal match review_signal='all'
    legacy_items = c.get(f"/api/v1/datasets/{d['id']}/items", params={"q": "alpha"}).json()
    explicit_all = c.get(f"/api/v1/datasets/{d['id']}/items", params={"q": "alpha", "review_signal": "all"}).json()
    assert [i["id"] for i in legacy_items["items"]] == [i["id"] for i in explicit_all["items"]]

    filter_cases = [
        {"q": "alpha", "topic": 4, "review_signal": "model_uncertain", "label_source": "effective"},
        {"q": "alpha", "sentiment": 2, "review_signal": "model_uncertain", "label_source": "ai", "run_id": run1["id"]},
        {"q": "alpha", "sentiment": 2, "review_signal": "model_uncertain", "label_source": "effective"},
        {"review_signal": "pending_signal_review", "review_status": "unreviewed"},
        {"q": "alpha", "review_signal": "truncated"},
    ]
    for fparams in filter_cases:
        page_res = c.get(f"/api/v1/datasets/{d['id']}/items", params={**fparams, "page_size": 2}).json()
        full_list = c.get(f"/api/v1/datasets/{d['id']}/items", params={**fparams, "page_size": 500}).json()
        summary = c.get(f"/api/v1/datasets/{d['id']}/summary", params=fparams).json()
        export_meta = c.post(f"/api/v1/datasets/{d['id']}/exports", json={**fparams, "scope": "filtered"}).json()
        csv_text = c.get(export_meta["url"]).content.decode("utf-8-sig")
        csv_rows = list(csv.DictReader(io.StringIO(csv_text)))

        assert page_res["total"] == summary["total"] == summary["attention"]["filtered_count"] == export_meta["row_count"]
        assert {i["id"] for i in full_list["items"]} == {row["item_id"] for row in csv_rows}

    # scope='all' ignores review_signal/q/sentiment/topic/review_status while honoring run_id & label_source
    all_export = c.post(
        f"/api/v1/datasets/{d['id']}/exports",
        json=dict(
            scope="all",
            q="alpha",
            sentiment=2,
            review_signal="model_uncertain",
            label_source="ai",
            run_id=run1["id"],
        ),
    ).json()
    assert all_export["row_count"] == 4
    all_rows = list(csv.DictReader(io.StringIO(c.get(all_export["url"]).content.decode("utf-8-sig"))))
    first_csv = next(row for row in all_rows if row["item_id"] == first["id"])
    assert first_csv["selected_sentiment"] == "2"
    assert first_csv["effective_sentiment"] == "1"


def test_export_csv_columns_policy_snapshot_and_byte_immutability(env, monkeypatch, tmp_path):
    c, store, r, w = env
    clear_t = [0.82] + [0.02] * 9
    r.specs = {
        "câu yếu": {"sentiment_scores": [0.50, 0.30, 0.10, 0.10], "topic_scores": clear_t},
        "câu rõ": {"sentiment_scores": [0.85, 0.05, 0.05, 0.05], "topic_scores": clear_t},
    }
    d = make_dataset(c, profile="neu", items=[dict(text="câu yếu"), dict(text="câu rõ")])
    create_run(c, d)
    drain(w)

    export_res = c.post(
        f"/api/v1/datasets/{d['id']}/exports",
        json=dict(scope="filtered", review_signal="pending_signal_review"),
    )
    assert export_res.status_code == 201, export_res.text
    export_meta = export_res.json()
    assert export_meta["row_count"] == 1

    before_bytes = c.get(export_meta["url"]).content
    reader = csv.reader(io.StringIO(before_bytes.decode("utf-8-sig")))
    header = next(reader)
    assert header == EXPECTED_CSV_COLUMNS

    # Verify stored exports.filters retains review_policy snapshot
    with store.connect() as db:
        stored_row = db.execute("SELECT filters FROM exports WHERE id=?", (export_meta["id"],)).fetchone()
    stored_filters = json.loads(stored_row["filters"])
    assert stored_filters["review_signal"] == "pending_signal_review"
    assert stored_filters["review_policy"]["id"] == "review-signals-v1"
    assert stored_filters["review_policy"]["hash"] == load_policy(DEFAULT_POLICY_PATH)["hash"]
    assert stored_filters["review_policy"]["schema_id"] == "neu-v1"

    # Mutate review, append new row, change policy in-process, restart app -> GET old export byte-identical
    weak_item = c.get(f"/api/v1/datasets/{d['id']}/items", params={"review_signal": "pending_signal_review"}).json()["items"][0]
    assert c.put(
        f"/api/v1/items/{weak_item['id']}/review",
        json=dict(
            task="sentiment",
            status="confirmed",
            label_id=0,
            expected_revision=1,
            expected_review_revision=0,
            source_prediction_id=weak_item["prediction"]["id"],
        ),
    ).status_code == 200
    assert c.post(
        f"/api/v1/datasets/{d['id']}/items",
        json=dict(items=[dict(text="câu mới thêm")]),
    ).status_code == 201

    _install_custom_default_policy(monkeypatch, tmp_path, {
        "id": "review-signals-v2",
        "experimental": True,
        "schemas": {
            "neu-v1": {
                "sentiment": {"top1_min": 0.99, "margin_min": 0.90},
                "topic": {"top1_min": 0.99, "margin_min": 0.90},
            },
            "uit-v1": {
                "sentiment": {"top1_min": 0.99, "margin_min": 0.90},
                "topic": {"top1_min": 0.99, "margin_min": 0.90},
            },
        },
    })

    with TestClient(create_app(store.runtime, r)) as restarted:
        after_bytes = restarted.get(export_meta["url"]).content
        assert after_bytes == before_bytes


def test_corrupt_sqlite_prediction_payloads_do_not_crash_endpoints(env):
    c, store, _r, w = env
    texts = [
        "corrupt-empty-scores",
        "corrupt-missing-topic",
        "corrupt-sentiment-null",
        "corrupt-nan-scores",
        "corrupt-non-int-label",
        "healthy-clear-reviewed",
    ]
    d = make_dataset(c, profile="neu", items=[dict(text=t) for t in texts])
    create_run(c, d)
    drain(w)

    items_by_text = {
        i["text"]: i
        for i in c.get(f"/api/v1/datasets/{d['id']}/items", params={"page_size": 500}).json()["items"]
    }

    # Confirm both tasks on the healthy item so legacy review_status=needs_review excludes it
    healthy = items_by_text["healthy-clear-reviewed"]
    for task in ("sentiment", "topic"):
        res = c.put(
            f"/api/v1/items/{healthy['id']}/review",
            json=dict(
                task=task,
                status="confirmed",
                label_id=healthy["prediction"][task]["label_id"],
                expected_revision=1,
                expected_review_revision=0,
                source_prediction_id=healthy["prediction"]["id"],
            ),
        )
        assert res.status_code == 200, res.text

    valid_topic = {"label_id": 0, "scores": [0.82] + [0.02] * 9}
    valid_sentiment = {"label_id": 0, "scores": [0.85, 0.05, 0.05, 0.05]}

    corrupt_payloads = {
        "corrupt-empty-scores": json.dumps({
            "item_id": items_by_text["corrupt-empty-scores"]["id"],
            "revision_id": items_by_text["corrupt-empty-scores"]["revision_id"],
            "model_id": "test-double-neu",
            "model_version": "v1",
            "schema_id": "neu-v1",
            "sentiment": {"label_id": 0, "scores": []},
            "topic": valid_topic,
            "token_count_before_truncation": 5,
            "truncated": False,
            "warnings": [],
            "duration_ms": 1.0,
        }),
        "corrupt-missing-topic": json.dumps({
            "item_id": items_by_text["corrupt-missing-topic"]["id"],
            "revision_id": items_by_text["corrupt-missing-topic"]["revision_id"],
            "model_id": "test-double-neu",
            "model_version": "v1",
            "schema_id": "neu-v1",
            "sentiment": valid_sentiment,
            # "topic" omitted intentionally
            "token_count_before_truncation": 5,
            "truncated": False,
            "warnings": [],
            "duration_ms": 1.0,
        }),
        "corrupt-sentiment-null": json.dumps({
            "item_id": items_by_text["corrupt-sentiment-null"]["id"],
            "revision_id": items_by_text["corrupt-sentiment-null"]["revision_id"],
            "model_id": "test-double-neu",
            "model_version": "v1",
            "schema_id": "neu-v1",
            "sentiment": None,
            "topic": valid_topic,
            "token_count_before_truncation": 5,
            "truncated": False,
            "warnings": [],
            "duration_ms": 1.0,
        }),
        "corrupt-nan-scores": (
            '{"item_id":"' + items_by_text["corrupt-nan-scores"]["id"] + '",'
            '"revision_id":"' + items_by_text["corrupt-nan-scores"]["revision_id"] + '",'
            '"model_id":"test-double-neu","model_version":"v1","schema_id":"neu-v1",'
            '"sentiment":{"label_id":0,"scores":[0.5,NaN,0.25,0.25]},'
            '"topic":' + json.dumps(valid_topic) + ','
            '"token_count_before_truncation":5,"truncated":false,"warnings":[],"duration_ms":1.0}'
        ),
        "corrupt-non-int-label": json.dumps({
            "item_id": items_by_text["corrupt-non-int-label"]["id"],
            "revision_id": items_by_text["corrupt-non-int-label"]["revision_id"],
            "model_id": "test-double-neu",
            "model_version": "v1",
            "schema_id": "neu-v1",
            "sentiment": {"label_id": "bad", "scores": [0.85, 0.05, 0.05, 0.05]},
            "topic": valid_topic,
            "token_count_before_truncation": 5,
            "truncated": False,
            "warnings": [],
            "duration_ms": 1.0,
        }),
    }

    with store.tx() as db:
        for text_key, raw_payload in corrupt_payloads.items():
            pred_id = items_by_text[text_key]["prediction"]["id"]
            db.execute("UPDATE predictions SET payload=? WHERE id=?", (raw_payload, pred_id))

    expected_corrupt_tasks = {
        "corrupt-empty-scores": ("sentiment",),
        "corrupt-missing-topic": ("topic",),
        "corrupt-sentiment-null": ("sentiment",),
        "corrupt-nan-scores": ("sentiment",),
        "corrupt-non-int-label": ("sentiment",),
    }

    # 1. GET /items/{id} never crashes and reports INVALID_SCORES for each corrupt task
    for text_key, bad_tasks in expected_corrupt_tasks.items():
        res = c.get(f"/api/v1/items/{items_by_text[text_key]['id']}")
        assert res.status_code == 200, f"{text_key}: {res.text}"
        detail = res.json()
        for task in bad_tasks:
            assert detail["review_signals"][task]["state"] == "unavailable"
            assert detail["review_signals"][task]["reasons"] == ["INVALID_SCORES"]
        if text_key in ("corrupt-missing-topic", "corrupt-sentiment-null", "corrupt-non-int-label"):
            for task in bad_tasks:
                assert detail["effective"][task] is None

    # 2. GET /items with both review_status=all and review_status=needs_review succeed (200)
    list_all_res = c.get(f"/api/v1/datasets/{d['id']}/items", params={"review_status": "all", "page_size": 500})
    assert list_all_res.status_code == 200, list_all_res.text
    list_all = list_all_res.json()
    assert list_all["total"] == 6
    by_text_all = {i["text"]: i for i in list_all["items"]}
    for text_key, bad_tasks in expected_corrupt_tasks.items():
        for task in bad_tasks:
            assert by_text_all[text_key]["review_signals"][task]["state"] == "unavailable"
            assert by_text_all[text_key]["review_signals"][task]["reasons"] == ["INVALID_SCORES"]

    needs_res = c.get(f"/api/v1/datasets/{d['id']}/items", params={"review_status": "needs_review", "page_size": 500})
    assert needs_res.status_code == 200, needs_res.text
    needs_texts = {i["text"] for i in needs_res.json()["items"]}
    # Healthy 2/2-reviewed clear item stays excluded; all 5 corrupt unreviewed items remain listed
    assert needs_texts == set(corrupt_payloads)

    sorted_ai_res = c.get(
        f"/api/v1/datasets/{d['id']}/items",
        params={"label_source": "ai", "sort": "sentiment", "page_size": 500},
    )
    assert sorted_ai_res.status_code == 200, sorted_ai_res.text

    # 3. GET /summary succeeds in both effective and ai label sources
    for label_source in ("effective", "ai"):
        sum_res = c.get(f"/api/v1/datasets/{d['id']}/summary", params={"label_source": label_source})
        assert sum_res.status_code == 200, sum_res.text
        sum_body = sum_res.json()
        assert sum_body["total"] == 6
        assert sum_body["attention"]["filtered_count"] == 6

    # 4. POST /exports & CSV download succeed without HTTP 500
    for export_body in (
        {"scope": "filtered", "review_status": "needs_review"},
        {"scope": "all"},
    ):
        exp_res = c.post(f"/api/v1/datasets/{d['id']}/exports", json=export_body)
        assert exp_res.status_code == 201, exp_res.text
        exp_meta = exp_res.json()
        dl_res = c.get(exp_meta["url"])
        assert dl_res.status_code == 200
        rows = list(csv.DictReader(io.StringIO(dl_res.content.decode("utf-8-sig"))))
        assert len(rows) == exp_meta["row_count"]
        assert list(rows[0].keys()) == EXPECTED_CSV_COLUMNS

    # 5. PUT /review confirmed on missing task dict or non-int label_id returns 409 CONFIRM_REQUIRES_PREDICTION
    for text_key, task in (
        ("corrupt-missing-topic", "topic"),
        ("corrupt-sentiment-null", "sentiment"),
        ("corrupt-non-int-label", "sentiment"),
    ):
        item_obj = items_by_text[text_key]
        rev_res = c.put(
            f"/api/v1/items/{item_obj['id']}/review",
            json=dict(
                task=task,
                status="confirmed",
                label_id=0,
                expected_revision=1,
                expected_review_revision=0,
                source_prediction_id=item_obj["prediction"]["id"],
            ),
        )
        assert rev_res.status_code == 409, f"{text_key}/{task}: {rev_res.text}"
        assert rev_res.json()["code"] == "CONFIRM_REQUIRES_PREDICTION"
