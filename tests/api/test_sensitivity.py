import csv
import hashlib
import io
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import MIGRATION_1, Store, encode, profile_for
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def env(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        yield client, app.state.store, registry, Worker(tmp_path, registry, batch_size=1)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utf16_span(text: str, needle: str, occurrence: int = 0) -> dict:
    pos = 0
    start = -1
    for _ in range(occurrence + 1):
        start = text.find(needle, pos)
        assert start != -1, f"{needle!r} not in {text!r}"
        pos = start + 1
    end = start + len(needle)
    return {
        "start_utf16": len(text[:start].encode("utf-16-le")) // 2,
        "end_utf16": len(text[:end].encode("utf-16-le")) // 2,
        "text": needle,
    }


def _create_dataset(client, profile="neu", texts=None, name="Độ nhạy"):
    resp = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "profile": profile,
            "items": [{"text": t} for t in (texts or ["Dịch vụ rất tốt luôn", "Phòng học hơi nóng nhưng ổn"])],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _items(client, dataset_id, **params):
    resp = client.get(f"/api/v1/datasets/{dataset_id}/items", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _drain(worker):
    for _ in range(200):
        if not worker.run_once():
            return
    raise AssertionError("Worker did not drain")


def _build_payload(item: dict, needle: str, occurrence: int = 0, run_id=None) -> dict:
    return {
        "revision_id": item["revision_id"],
        "expected_revision": item["revision"],
        "text_sha256": _sha256(item["text"]),
        "run_id": run_id,
        "source_prediction_id": item["prediction"]["id"] if item["prediction"] else None,
        "selection": _utf16_span(item["text"], needle, occurrence),
    }


def _table_counts(store: Store) -> dict[str, int]:
    tables = (
        "datasets",
        "items",
        "revisions",
        "runs",
        "run_items",
        "predictions",
        "jobs",
        "sensitivity_experiments",
        "sensitivity_rate_limits",
        "idempotency",
    )
    with store.connect() as db:
        return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_request_validation_and_idempotency_conflict_matrix(env):
    client, store, _, _ = env
    ds = _create_dataset(client, profile="neu", texts=["Dịch vụ rất tốt luôn", "Giảng viên rất nhiệt tình"])
    run_resp = client.post("/api/v1/analysis-runs", json={"dataset_id": ds["id"]})
    assert run_resp.status_code == 202
    item0, item1 = _items(client, ds["id"])
    valid = _build_payload(item0, "rất tốt")

    # Missing or blank Idempotency-Key -> 422 VALIDATION_ERROR.
    assert client.post(f"/api/v1/items/{item0['id']}/sensitivity-experiments", json=valid).json()["code"] == "VALIDATION_ERROR"
    blank_resp = client.post(
        f"/api/v1/items/{item0['id']}/sensitivity-experiments",
        json=valid,
        headers={"Idempotency-Key": "   "},
    )
    assert blank_resp.status_code == 422 and blank_resp.json()["code"] == "VALIDATION_ERROR"

    # Missing required nullable field or extra/invalid shape fields -> 422 VALIDATION_ERROR.
    missing_pred = dict(valid)
    del missing_pred["source_prediction_id"]
    for bad_body in (
        missing_pred,
        {**valid, "extra_field": 1},
        {**valid, "baseline_scores": [1, 0]},
        {**valid, "variant_text": "tamper"},
        {**valid, "expected_revision": 0},
        {**valid, "expected_revision": True},
        {**valid, "selection": {**valid["selection"], "start_utf16": True}},
        {**valid, "selection": {**valid["selection"], "end_utf16": 1.5}},
        {**valid, "selection": {**valid["selection"], "extra": "x"}},
    ):
        resp = client.post(
            f"/api/v1/items/{item0['id']}/sensitivity-experiments",
            json=bad_body,
            headers={"Idempotency-Key": "bad-shape"},
        )
        assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"

    # Valid POST + exact replay.
    headers = {"Idempotency-Key": "idem-matrix-1"}
    created = client.post(f"/api/v1/items/{item0['id']}/sensitivity-experiments", json=valid, headers=headers)
    assert created.status_code == 202, created.text
    exp = created.json()
    counts_after_create = _table_counts(store)

    replayed = client.post(f"/api/v1/items/{item0['id']}/sensitivity-experiments", json=valid, headers=headers)
    assert replayed.status_code == 202
    assert replayed.json()["experiment_id"] == exp["experiment_id"]
    assert _table_counts(store) == counts_after_create

    # Any change with the same key (item_id or any body/selection field) -> 409 IDEMPOTENCY_CONFLICT.
    assert (
        client.post(
            f"/api/v1/items/{item1['id']}/sensitivity-experiments",
            json=valid,
            headers=headers,
        ).status_code
        == 409
    )
    mutations = [
        {**valid, "revision_id": "different-rev"},
        {**valid, "expected_revision": 2},
        {**valid, "text_sha256": _sha256("other")},
        {**valid, "run_id": run_resp.json()["id"]},
        {**valid, "source_prediction_id": "different-pred"},
        {**valid, "selection": {**valid["selection"], "start_utf16": valid["selection"]["start_utf16"] + 1}},
        {**valid, "selection": {**valid["selection"], "end_utf16": valid["selection"]["end_utf16"] - 1}},
        {**valid, "selection": {**valid["selection"], "text": "khác"}},
    ]
    for mutated in mutations:
        conflict = client.post(
            f"/api/v1/items/{item0['id']}/sensitivity-experiments",
            json=mutated,
            headers=headers,
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert _table_counts(store) == counts_after_create


def test_live_ttl_replay_bypasses_staleness_model_and_quota_then_expires_cleanly(env):
    client, store, registry, worker = env
    ds = _create_dataset(client, profile="neu", texts=["Dịch vụ rất tốt luôn"])
    item = _items(client, ds["id"])[0]
    payload = _build_payload(item, "rất tốt")
    headers = {"Idempotency-Key": "ttl-replay-key"}

    first = client.post(f"/api/v1/items/{item['id']}/sensitivity-experiments", json=payload, headers=headers)
    assert first.status_code == 202
    exp_id = first.json()["experiment_id"]
    _drain(worker)
    completed = client.get(f"/api/v1/sensitivity-experiments/{exp_id}").json()
    assert completed["status"] == "completed" and completed["result"] is not None

    # Mutate source text (makes source stale), swap and remove model, and saturate rate limits.
    edit_resp = client.patch(
        f"/api/v1/items/{item['id']}/text",
        json={"text": "Văn bản nguồn đã thay đổi", "expected_revision": 1},
    )
    assert edit_resp.status_code == 200
    registry.model_version = "v-changed"
    registry.available = False
    now_ts = time.time()
    with store.tx() as db:
        for idx in range(12):
            db.execute("INSERT INTO sensitivity_rate_limits VALUES(?,?)", (f"sat-{idx}", now_ts))
    rate_before = _table_counts(store)["sensitivity_rate_limits"]

    replayed = client.post(f"/api/v1/items/{item['id']}/sensitivity-experiments", json=payload, headers=headers)
    assert replayed.status_code == 202
    replayed_json = replayed.json()
    assert replayed_json["experiment_id"] == exp_id
    assert replayed_json["source_stale"] is True
    assert replayed_json["result"]["baseline"]["text"] == "Dịch vụ rất tốt luôn"
    assert _table_counts(store)["sensitivity_rate_limits"] == rate_before

    # Force TTL expiration + clear synthetic rate limit blockers -> idempotency row purged, same key creates new job.
    registry.available = True
    with store.tx() as db:
        db.execute("UPDATE datasets SET expires_at=? WHERE temporary=1", (time.time() - 10,))
        db.execute("DELETE FROM sensitivity_rate_limits")
    store.cleanup()

    assert client.get(f"/api/v1/sensitivity-experiments/{exp_id}").status_code == 404
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM idempotency WHERE key=? AND operation='sensitivity'",
                ("ttl-replay-key",),
            ).fetchone()[0]
            == 0
        )

    edited_item = client.get(f"/api/v1/items/{item['id']}").json()
    second_payload = _build_payload(edited_item, "đã thay đổi")
    recreated = client.post(
        f"/api/v1/items/{item['id']}/sensitivity-experiments",
        json=second_payload,
        headers=headers,
    )
    assert recreated.status_code == 202
    assert recreated.json()["experiment_id"] != exp_id


def test_source_context_run_scope_nullable_prediction_and_revisions(env):
    client, store, _, worker = env
    ds1 = _create_dataset(client, profile="neu", texts=["Môn học rất hay luôn"])
    ds2 = _create_dataset(client, profile="neu", texts=["Dataset khác"])
    run_ds2 = client.post("/api/v1/analysis-runs", json={"dataset_id": ds2["id"]}).json()

    # Unprocessed item with source_prediction_id=None succeeds; fake prediction ID fails 409.
    raw_item = _items(client, ds1["id"])[0]
    bad_null_mismatch = client.post(
        f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
        json={**_build_payload(raw_item, "rất hay"), "source_prediction_id": "nonexistent-pred"},
        headers={"Idempotency-Key": "src-fake-pred"},
    )
    assert bad_null_mismatch.status_code == 409 and bad_null_mismatch.json()["code"] == "SOURCE_CONTEXT_CHANGED"

    no_pred_resp = client.post(
        f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
        json=_build_payload(raw_item, "rất hay"),
        headers={"Idempotency-Key": "src-no-pred"},
    )
    assert no_pred_resp.status_code == 202
    no_pred_json = no_pred_resp.json()
    assert no_pred_json["source"]["prediction_id"] is None
    assert no_pred_json["source"]["resolved_run_id"] is None
    assert no_pred_json["execution"]["baseline_recomputed"] is True
    assert no_pred_json["execution"]["source_model_changed"] is False
    _drain(worker)

    # Genuine completed quick source is supported and retains its exact run identity.
    quick = client.post("/api/v1/quick-analysis", json={"profile": "neu", "text": "Câu tạm để thử"}).json()
    _drain(worker)
    quick_ds_id = store.run(quick["run_id"])["dataset_id"]
    quick_item_id = _items(client, quick_ds_id)[0]["id"]
    quick_item = client.get(f"/api/v1/items/{quick_item_id}").json()
    quick_exp = client.post(
        f"/api/v1/items/{quick_item_id}/sensitivity-experiments",
        json=_build_payload(quick_item, "tạm", run_id=quick["run_id"]),
        headers={"Idempotency-Key": "src-quick-temp"},
    )
    assert quick_exp.status_code == 202, quick_exp.text
    assert quick_exp.json()["source"]["resolved_run_id"] == quick["run_id"]
    assert quick_exp.json()["source"]["prediction_id"] == quick_item["prediction"]["id"]
    _drain(worker)

    # Sensitivity temp item (baseline_item_id) is also rejected as INVALID_EXPERIMENT_SOURCE.
    with store.connect() as db:
        sens_base_id = db.execute(
            "SELECT baseline_item_id FROM sensitivity_experiments WHERE job_id=?",
            (no_pred_json["job_id"],),
        ).fetchone()["baseline_item_id"]
    sens_base_item = client.get(f"/api/v1/items/{sens_base_id}").json()
    assert (
        client.post(
            f"/api/v1/items/{sens_base_id}/sensitivity-experiments",
            json=_build_payload(sens_base_item, "rất hay"),
            headers={"Idempotency-Key": "src-sens-temp"},
        ).json()["code"]
        == "INVALID_EXPERIMENT_SOURCE"
    )

    # 404 item / 404 run / 422 RUN_DATASET_MISMATCH.
    assert (
        client.post(
            "/api/v1/items/missing-item/sensitivity-experiments",
            json=_build_payload(raw_item, "rất hay"),
            headers={"Idempotency-Key": "src-404-item"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
            json=_build_payload(raw_item, "rất hay", run_id="missing-run"),
            headers={"Idempotency-Key": "src-404-run"},
        ).status_code
        == 404
    )
    mismatch_resp = client.post(
        f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
        json=_build_payload(raw_item, "rất hay", run_id=run_ds2["id"]),
        headers={"Idempotency-Key": "src-run-mismatch"},
    )
    assert mismatch_resp.status_code == 422 and mismatch_resp.json()["code"] == "RUN_DATASET_MISMATCH"

    # Complete run1 on ds1, then run2 on same unchanged revision.
    run1 = client.post("/api/v1/analysis-runs", json={"dataset_id": ds1["id"]}).json()
    _drain(worker)
    item_after_run1 = client.get(f"/api/v1/items/{raw_item['id']}").json()
    pred1_id = item_after_run1["prediction"]["id"]
    assert pred1_id is not None

    # Passing null or wrong source_prediction_id when prediction exists -> 409 SOURCE_CONTEXT_CHANGED.
    for wrong_pred in (None, "other-pred"):
        resp = client.post(
            f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
            json={**_build_payload(item_after_run1, "rất hay"), "source_prediction_id": wrong_pred},
            headers={"Idempotency-Key": f"src-changed-{wrong_pred}"},
        )
        assert resp.status_code == 409 and resp.json()["code"] == "SOURCE_CONTEXT_CHANGED"

    # Revision / hash conflicts -> 409 REVISION_CONFLICT.
    for bad_rev in (
        {**_build_payload(item_after_run1, "rất hay"), "revision_id": "wrong-rev"},
        {**_build_payload(item_after_run1, "rất hay"), "expected_revision": 9},
        {**_build_payload(item_after_run1, "rất hay"), "text_sha256": _sha256("other text")},
    ):
        resp = client.post(
            f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
            json=bad_rev,
            headers={"Idempotency-Key": f"src-rev-{hash(json.dumps(bad_rev, sort_keys=True))}"},
        )
        assert resp.status_code == 409 and resp.json()["code"] == "REVISION_CONFLICT"

    # Historical run_id whose revision is STILL current is allowed.
    run2 = client.post("/api/v1/analysis-runs", json={"dataset_id": ds1["id"]}).json()
    _drain(worker)
    hist_same_rev = client.get(f"/api/v1/items/{raw_item['id']}", params={"run_id": run1["id"]}).json()
    assert hist_same_rev["stale"] is False
    ok_hist = client.post(
        f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
        json=_build_payload(hist_same_rev, "rất hay", run_id=run1["id"]),
        headers={"Idempotency-Key": "src-hist-current-rev"},
    )
    assert ok_hist.status_code == 202
    assert ok_hist.json()["source"]["selected_run_id"] == run1["id"]
    assert ok_hist.json()["source"]["resolved_run_id"] == run1["id"]
    assert ok_hist.json()["source"]["prediction_id"] == pred1_id
    _drain(worker)

    # Edit text -> rev2: submitting against stale run1 returns 409 REVISION_CONFLICT.
    client.patch(f"/api/v1/items/{raw_item['id']}/text", json={"text": "Nội dung mới hoàn toàn", "expected_revision": 1})
    stale_hist = client.get(f"/api/v1/items/{raw_item['id']}", params={"run_id": run1["id"]}).json()
    assert stale_hist["stale"] is True
    stale_resp = client.post(
        f"/api/v1/items/{raw_item['id']}/sensitivity-experiments",
        json=_build_payload(stale_hist, "rất hay", run_id=run1["id"]),
        headers={"Idempotency-Key": "src-stale-hist"},
    )
    assert stale_resp.status_code == 409 and stale_resp.json()["code"] == "REVISION_CONFLICT"

    # Failed calls above did not leak extra rate entries beyond the 2 valid creations.
    assert _table_counts(store)["sensitivity_rate_limits"] == 3  # Includes the supported quick experiment.


def test_concurrent_idempotent_post_and_atomic_quotas(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        store = app.state.store
        worker = Worker(tmp_path, registry, batch_size=1)
        texts = [f"Phản hồi thử nghiệm số {idx} rất ổn" for idx in range(12)]
        ds = _create_dataset(client, profile="neu", texts=texts)
        all_items = _items(client, ds["id"], page_size=25)

        # 1. Concurrent identical POSTs with same Idempotency-Key create exactly 1 experiment.
        payload0 = _build_payload(all_items[0], "rất ổn")

        def submit_same(_):
            return client.post(
                f"/api/v1/items/{all_items[0]['id']}/sensitivity-experiments",
                json=payload0,
                headers={"Idempotency-Key": "concurrent-same-key"},
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(submit_same, range(6)))
        assert all(r.status_code == 202 for r in responses)
        exp_ids = {r.json()["experiment_id"] for r in responses}
        assert len(exp_ids) == 1
        active0_id = next(iter(exp_ids))
        assert _table_counts(store)["sensitivity_experiments"] == 1
        assert _table_counts(store)["sensitivity_rate_limits"] == 1

        # 2. Per-item active limit -> 409 EXPERIMENT_IN_PROGRESS with existing_job_id; consumes 0 rate quota.
        dup_item = client.post(
            f"/api/v1/items/{all_items[0]['id']}/sensitivity-experiments",
            json=payload0,
            headers={"Idempotency-Key": "per-item-blocked"},
        )
        assert dup_item.status_code == 409
        assert dup_item.json()["code"] == "EXPERIMENT_IN_PROGRESS"
        assert dup_item.json()["details"] == {"existing_job_id": active0_id}
        assert _table_counts(store)["sensitivity_rate_limits"] == 1

        # 3. Runtime-wide active limit (4): create 3 more active jobs (total 4), 5th fails 429 CONCURRENT_LIMIT.
        active_ids = [active0_id]
        for idx in range(1, 4):
            r = client.post(
                f"/api/v1/items/{all_items[idx]['id']}/sensitivity-experiments",
                json=_build_payload(all_items[idx], "rất ổn"),
                headers={"Idempotency-Key": f"active-{idx}"},
            )
            assert r.status_code == 202
            active_ids.append(r.json()["experiment_id"])
        assert _table_counts(store)["sensitivity_experiments"] == 4

        fifth = client.post(
            f"/api/v1/items/{all_items[4]['id']}/sensitivity-experiments",
            json=_build_payload(all_items[4], "rất ổn"),
            headers={"Idempotency-Key": "active-5-blocked"},
        )
        assert fifth.status_code == 429
        assert fifth.json()["code"] == "EXPERIMENT_LIMIT"
        assert fifth.json()["details"]["limit"] == 4
        assert fifth.json()["details"]["reason"] == "CONCURRENT_LIMIT"
        assert _table_counts(store)["sensitivity_experiments"] == 4
        assert _table_counts(store)["sensitivity_rate_limits"] == 4

        # Drain active jobs so active count drops to 0, freeing concurrent slot while rate stays at 4/10.
        _drain(worker)
        for idx in range(4, 10):
            r = client.post(
                f"/api/v1/items/{all_items[idx]['id']}/sensitivity-experiments",
                json=_build_payload(all_items[idx], "rất ổn"),
                headers={"Idempotency-Key": f"rate-{idx}"},
            )
            assert r.status_code == 202
            assert client.post(f"/api/v1/jobs/{r.json()['job_id']}/cancel").status_code == 200
        assert _table_counts(store)["sensitivity_rate_limits"] == 10

        # 11th creation in 60s hits RATE_LIMIT -> 429 with retry_after_seconds and creates 0 orphan rows.
        ds_count_before = _table_counts(store)["datasets"]
        exp_count_before = _table_counts(store)["sensitivity_experiments"]
        eleventh = client.post(
            f"/api/v1/items/{all_items[10]['id']}/sensitivity-experiments",
            json=_build_payload(all_items[10], "rất ổn"),
            headers={"Idempotency-Key": "rate-11-blocked"},
        )
        assert eleventh.status_code == 429
        body_11 = eleventh.json()
        assert body_11["code"] == "EXPERIMENT_LIMIT"
        assert body_11["details"]["limit"] == 10
        assert body_11["details"]["reason"] == "RATE_LIMIT"
        assert 1 <= body_11["details"]["retry_after_seconds"] <= 60
        assert _table_counts(store)["datasets"] == ds_count_before
        assert _table_counts(store)["sensitivity_experiments"] == exp_count_before

        # Aging rate-limit entries (>60s old) frees rate quota automatically on next transaction.
        with store.tx() as db:
            db.execute("UPDATE sensitivity_rate_limits SET created_ts=?", (time.time() - 61.0,))
        unblocked = client.post(
            f"/api/v1/items/{all_items[10]['id']}/sensitivity-experiments",
            json=_build_payload(all_items[10], "rất ổn"),
            headers={"Idempotency-Key": "rate-after-window"},
        )
        assert unblocked.status_code == 202


def test_atomic_rollback_on_mid_creation_sqlite_failure(tmp_path, monkeypatch):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app, raise_server_exceptions=False) as client:
        store = app.state.store
        ds = _create_dataset(client, profile="neu", texts=["Kiểm tra rollback giao dịch rất ổn"])
        item = _items(client, ds["id"])[0]
        payload = _build_payload(item, "rất ổn")
        before = _table_counts(store)

        # Case A: Fail inside _create_run_tx AFTER temp dataset + items + revisions were written.
        orig_create_run_tx = store._create_run_tx

        def fail_run_tx(c, dataset_id, model, **kwargs):
            orig_create_run_tx(c, dataset_id, model, **kwargs)
            raise sqlite3.OperationalError("simulated failure after _create_run_tx")

        monkeypatch.setattr(store, "_create_run_tx", fail_run_tx)
        resp_a = client.post(
            f"/api/v1/items/{item['id']}/sensitivity-experiments",
            json=payload,
            headers={"Idempotency-Key": "rollback-a"},
        )
        assert resp_a.status_code == 500
        assert _table_counts(store) == before
        monkeypatch.undo()

        # Case B: Fail inside final remember() AFTER sensitivity_experiments & rate_limits inserts.
        orig_remember = store.remember

        def fail_final_remember(c, key, operation, body, result_id=None):
            if result_id is not None and operation == "sensitivity":
                raise sqlite3.OperationalError("simulated disk full during final idempotency insert")
            return orig_remember(c, key, operation, body, result_id=result_id)

        monkeypatch.setattr(store, "remember", fail_final_remember)
        resp_b = client.post(
            f"/api/v1/items/{item['id']}/sensitivity-experiments",
            json=payload,
            headers={"Idempotency-Key": "rollback-b"},
        )
        assert resp_b.status_code == 500
        assert _table_counts(store) == before
        monkeypatch.undo()

        # Subsequent valid request succeeds cleanly.
        ok = client.post(
            f"/api/v1/items/{item['id']}/sensitivity-experiments",
            json=payload,
            headers={"Idempotency-Key": "rollback-recovered"},
        )
        assert ok.status_code == 202


def test_health_version_and_v1_to_v2_migration_preserves_durable_data_and_export_bytes(tmp_path):
    # Construct a genuine schema v1 SQLite database containing durable dataset, revisions, predictions,
    # reviews, and a completed export before opening Store v2.
    db_path = tmp_path / "workspace.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    for stmt in MIGRATION_1.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.execute("INSERT INTO schema_migrations VALUES(1, '2026-11-01T00:00:00Z')")

    ds_id = "ds-v1-durable"
    item_id = "item-v1-1"
    rev1_id = "rev-v1-1"
    rev2_id = "rev-v1-2"
    run_id = "run-v1-1"
    job_id = "job-v1-1"
    pred_id = "pred-v1-1"
    review_id = "revw-v1-1"
    export_id = "exp-v1-1"

    conn.execute(
        "INSERT INTO datasets VALUES(?,?,?,?,?,?,0,NULL)",
        (ds_id, "Bộ dữ liệu v1", "neu", "neu-v1", "2026-11-01T00:00:00Z", "2026-11-01T00:05:00Z"),
    )
    conn.execute("INSERT INTO items VALUES(?,?,1,?)", (item_id, ds_id, rev2_id))
    t1 = "Nội dung v1 cũ"
    t2 = "Phòng học rất tốt nhưng điều hòa hơi ồn"
    conn.execute(
        "INSERT INTO revisions VALUES(?,?,1,?,?,?,?)",
        (rev1_id, item_id, t1, _sha256(t1), "{}", "2026-11-01T00:01:00Z"),
    )
    conn.execute(
        "INSERT INTO revisions VALUES(?,?,2,?,?,?,?)",
        (rev2_id, item_id, t2, _sha256(t2), encode({"khoa": "CNTT"}), "2026-11-01T00:02:00Z"),
    )
    conn.execute(
        "INSERT INTO runs VALUES(?,?,?,?,?,?,1,1,0,?)",
        (run_id, ds_id, "neu-v1", "TEST-DOUBLE-NOT-A-MODEL", "software-test-only-v1", "completed", "2026-11-01T00:03:00Z"),
    )
    conn.execute("INSERT INTO run_items VALUES(?,?,?,NULL)", (run_id, item_id, rev2_id))
    conn.execute(
        "INSERT INTO jobs(id,run_id,status,total,completed,failed,cancel_requested,attempt_id,created_at,updated_at,priority) "
        "VALUES(?,?,'completed',1,1,0,0,1,?,?,0)",
        (job_id, run_id, "2026-11-01T00:03:00Z", "2026-11-01T00:03:05Z"),
    )
    pred_payload = encode(
        {
            "item_id": item_id,
            "revision_id": rev2_id,
            "model_id": "TEST-DOUBLE-NOT-A-MODEL",
            "model_version": "software-test-only-v1",
            "schema_id": "neu-v1",
            "sentiment": {"label_id": 0, "scores": [0.7, 0.1, 0.1, 0.1]},
            "topic": {"label_id": 2, "scores": [0.05] * 2 + [0.55] + [0.05] * 7},
            "token_count_before_truncation": 12,
            "truncated": False,
            "warnings": [],
            "duration_ms": 1.2,
        }
    )
    conn.execute(
        "INSERT INTO predictions VALUES(?,?,?,?,?,?)",
        (pred_id, run_id, item_id, rev2_id, pred_payload, "2026-11-01T00:03:05Z"),
    )
    conn.execute(
        "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (review_id, item_id, rev2_id, "neu-v1", "sentiment", 1, "corrected", 1, "Bình luận trung tính", pred_id, "2026-11-01T00:04:00Z"),
    )
    v1_csv_bytes = (
        "\ufeffitem_id,source_row,text,effective_sentiment\r\n"
        f"{item_id},1,{t2},1\r\n"
    ).encode("utf-8-sig")
    conn.execute(
        "INSERT INTO exports VALUES(?,?,?,?,?,?,1,?)",
        (export_id, ds_id, run_id, "{}", "[]", sqlite3.Binary(v1_csv_bytes), "2026-11-01T00:05:00Z"),
    )
    conn.commit()
    conn.close()

    # Open Store / FastAPI app -> triggers MIGRATION_2.
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        store = app.state.store
        worker = Worker(tmp_path, registry, batch_size=1)

        health = client.get("/api/v1/health").json()
        assert health["database_version"] == 4

        with store.connect() as db:
            assert [r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2, 3, 4]
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert [r[0] for r in db.execute("PRAGMA integrity_check").fetchall()] == ["ok"]

        # Pre-existing durable export bytes, revisions, predictions, and reviews are intact.
        assert client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes
        migrated_item = client.get(f"/api/v1/items/{item_id}").json()
        assert migrated_item["revision"] == 2
        assert migrated_item["text"] == t2
        assert migrated_item["effective"]["sentiment"] == 1
        assert migrated_item["prediction"]["id"] == pred_id
        assert len(client.get(f"/api/v1/items/{item_id}/revisions").json()) == 2
        assert len(client.get(f"/api/v1/items/{item_id}/reviews").json()) == 1

        # Sensitivity experiment works seamlessly on migrated v1 item without altering old export bytes.
        exp = client.post(
            f"/api/v1/items/{item_id}/sensitivity-experiments",
            json=_build_payload(migrated_item, "rất tốt"),
            headers={"Idempotency-Key": "migrated-v1-exp"},
        )
        assert exp.status_code == 202
        _drain(worker)
        exp_done = client.get(f"/api/v1/sensitivity-experiments/{exp.json()['experiment_id']}").json()
        assert exp_done["status"] == "completed" and exp_done["result"] is not None
        assert client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes


def test_public_readonly_guards_block_sensitivity_temp_mutations_without_breaking_quick_analysis(env):
    client, store, _, worker = env
    ds = _create_dataset(client, profile="neu", texts=["Giảng viên nhiệt tình dễ hiểu"])
    item = _items(client, ds["id"])[0]

    exp = client.post(
        f"/api/v1/items/{item['id']}/sensitivity-experiments",
        json=_build_payload(item, "nhiệt tình"),
        headers={"Idempotency-Key": "readonly-guard-key"},
    ).json()
    _drain(worker)

    with store.connect() as db:
        row = db.execute(
            "SELECT temporary_dataset_id, baseline_item_id, variant_item_id FROM sensitivity_experiments WHERE job_id=?",
            (exp["job_id"],),
        ).fetchone()
    temp_ds_id = row["temporary_dataset_id"]
    baseline_id = row["baseline_item_id"]
    variant_id = row["variant_item_id"]

    # Every public dataset/item mutator targeting sensitivity temp records must fail with 409 EXPERIMENT_READ_ONLY.
    guard_calls = [
        client.patch(f"/api/v1/datasets/{temp_ds_id}", json={"name": "hack"}),
        client.delete(f"/api/v1/datasets/{temp_ds_id}"),
        client.post(f"/api/v1/datasets/{temp_ds_id}/copy", json={"name": "copy", "profile": "neu"}),
        client.post(f"/api/v1/datasets/{temp_ds_id}/items", json={"items": [{"text": "thêm"}]}),
        client.post("/api/v1/analysis-runs", json={"dataset_id": temp_ds_id}),
        client.post(f"/api/v1/datasets/{temp_ds_id}/exports", json={}),
        client.patch(f"/api/v1/items/{baseline_id}/text", json={"text": "sửa", "expected_revision": 1}),
        client.patch(f"/api/v1/items/{variant_id}/text", json={"text": "sửa", "expected_revision": 1}),
        client.put(
            f"/api/v1/items/{baseline_id}/review",
            json={"task": "sentiment", "status": "corrected", "label_id": 0, "expected_revision": 1, "expected_review_revision": 0},
        ),
        client.put(
            f"/api/v1/items/{variant_id}/review",
            json={"task": "sentiment", "status": "corrected", "label_id": 0, "expected_revision": 1, "expected_review_revision": 0},
        ),
        client.post(
            f"/api/v1/items/{baseline_id}/reviews/restore",
            json={"task": "sentiment", "review_revision": 1, "expected_revision": 1, "expected_review_revision": 0},
        ),
        client.post(
            f"/api/v1/items/{variant_id}/reviews/restore",
            json={"task": "sentiment", "review_revision": 1, "expected_revision": 1, "expected_review_revision": 0},
        ),
    ]
    for resp in guard_calls:
        assert resp.status_code == 409 and resp.json()["code"] == "EXPERIMENT_READ_ONLY"

    # Quick-analysis temp datasets continue working normally without EXPERIMENT_READ_ONLY interference.
    quick = client.post("/api/v1/quick-analysis", json={"profile": "neu", "text": "Thử nhanh vẫn bình thường"}).json()
    _drain(worker)
    q_job = client.get(f"/api/v1/jobs/{quick['job_id']}").json()
    assert q_job["kind"] == "quick" and q_job["status"] == "completed"
    assert q_job["result"]["text"] == "Thử nhanh vẫn bình thường"


def test_durable_isolation_source_delete_cascade_and_job_kind(env):
    client, store, _, worker = env
    ds = _create_dataset(client, profile="neu", texts=["Cơ sở vật chất rất tốt", "Học phí hợp lý"])
    run1 = client.post("/api/v1/analysis-runs", json={"dataset_id": ds["id"]}).json()
    _drain(worker)
    snapshot_ds_before = client.get(f"/api/v1/datasets/{ds['id']}").json()
    snapshot_runs_before = client.get(f"/api/v1/datasets/{ds['id']}/analysis-runs").json()
    snapshot_summary_before = client.get(f"/api/v1/datasets/{ds['id']}/summary").json()

    item0 = _items(client, ds["id"])[0]
    exp = client.post(
        f"/api/v1/items/{item0['id']}/sensitivity-experiments",
        json=_build_payload(item0, "rất tốt"),
        headers={"Idempotency-Key": "isolation-key"},
    ).json()

    # Pending job has kind='sensitivity' and result=None.
    pending_job = client.get(f"/api/v1/jobs/{exp['job_id']}").json()
    assert pending_job["kind"] == "sensitivity" and pending_job["result"] is None
    assert client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").json()["result"] is None

    _drain(worker)
    # Completed job STILL keeps result=None on /jobs/{id}; /sensitivity-experiments/{id} serves result.
    done_job = client.get(f"/api/v1/jobs/{exp['job_id']}").json()
    assert done_job["kind"] == "sensitivity" and done_job["status"] == "completed" and done_job["result"] is None

    # Source dataset list, items, runs, summary, and export remain completely isolated from temp rows.
    assert len(client.get("/api/v1/datasets").json()) == 1
    assert client.get(f"/api/v1/datasets/{ds['id']}").json() == snapshot_ds_before
    assert client.get(f"/api/v1/datasets/{ds['id']}/analysis-runs").json() == snapshot_runs_before
    assert client.get(f"/api/v1/datasets/{ds['id']}/summary").json() == snapshot_summary_before
    export = client.post(f"/api/v1/datasets/{ds['id']}/exports", json={}).json()
    csv_rows = list(csv.DictReader(io.StringIO(client.get(export["url"]).content.decode("utf-8-sig"))))
    assert len(csv_rows) == 2

    # Deleting source dataset atomically deletes linked temp dataset, sensitivity_experiments, and idempotency.
    assert client.delete(f"/api/v1/datasets/{ds['id']}").status_code == 204
    assert client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").status_code == 404
    assert client.get(f"/api/v1/jobs/{exp['job_id']}").status_code == 404
    for table in ("datasets", "items", "revisions", "runs", "run_items", "predictions", "jobs", "sensitivity_experiments", "idempotency"):
        assert _table_counts(store)[table] == 0


@pytest.mark.parametrize(("profile", "sent_n", "topic_n"), [("neu", 4, 10), ("uit", 3, 4)])
def test_comparison_math_for_neu_and_uit_plus_source_and_active_model_changes(env, profile, sent_n, topic_n):
    client, _, registry, worker = env
    ds = _create_dataset(client, profile=profile, texts=["Giảng viên rất nhiệt tình hỗ trợ sinh viên"])
    client.post("/api/v1/analysis-runs", json={"dataset_id": ds["id"]})
    _drain(worker)
    item = _items(client, ds["id"])[0]

    # Switch active model BEFORE creating experiment -> source_model_changed=True, baseline_recomputed=True.
    registry.model_version = "software-test-only-v2"
    created = client.post(
        f"/api/v1/items/{item['id']}/sensitivity-experiments",
        json=_build_payload(item, "rất nhiệt tình"),
        headers={"Idempotency-Key": f"cmp-{profile}"},
    ).json()
    assert created["execution"]["baseline_recomputed"] is True
    assert created["execution"]["source_model_changed"] is True
    assert created["execution"]["model_version"] == "software-test-only-v2"
    assert created["active_model_changed"] is False
    assert created["result"] is None

    _drain(worker)
    done = client.get(f"/api/v1/sensitivity-experiments/{created['experiment_id']}").json()
    assert done["status"] == "completed" and done["error"] is None and done["expires_at"] is not None
    res = done["result"]
    assert res["warnings"] == ["SENSITIVITY_NOT_CAUSAL"]

    for task, expected_len in (("sentiment", sent_n), ("topic", topic_n)):
        b_scores = res["baseline"]["prediction"][task]["scores"]
        v_scores = res["variant"]["prediction"][task]["scores"]
        cmp_task = res["comparison"][task]
        assert cmp_task["baseline_label_id"] == res["baseline"]["prediction"][task]["label_id"]
        assert cmp_task["variant_label_id"] == res["variant"]["prediction"][task]["label_id"]
        assert len(cmp_task["scores"]) == expected_len
        for idx, row in enumerate(cmp_task["scores"]):
            assert row["label_id"] == profile_for(profile)[task][idx]["id"]
            assert row["before"] == pytest.approx(b_scores[idx], abs=1e-12)
            assert row["after"] == pytest.approx(v_scores[idx], abs=1e-12)
            assert row["delta"] == pytest.approx(v_scores[idx] - b_scores[idx], abs=1e-12)

    # Switching or unloading model AFTER completion must preserve frozen result and report active_model_changed honestly.
    registry.model_version = "software-test-only-v3"
    after_swap = client.get(f"/api/v1/sensitivity-experiments/{created['experiment_id']}").json()
    assert after_swap["active_model_changed"] is True
    assert after_swap["execution"]["model_version"] == "software-test-only-v2"
    assert after_swap["result"] == res

    registry.available = False
    while_unavailable = client.get(f"/api/v1/sensitivity-experiments/{created['experiment_id']}").json()
    assert while_unavailable["result"] == res


def test_truncation_warnings_and_sensitivity_retry_guards(env):
    client, store, registry, worker = env
    # >128 words triggers truncated=True in TestOnlyRegistry.
    long_text = " ".join(["tot"] * 130 + ["xau"] * 5)
    ds = _create_dataset(client, profile="neu", texts=[long_text, "Câu ngắn bình thường", "Câu ba", "Câu bốn", "Câu năm"])
    items = _items(client, ds["id"])

    # 1. Both truncated + model_input_equal=True.
    registry.pair_input_equal_override = True
    exp1 = client.post(
        f"/api/v1/items/{items[0]['id']}/sensitivity-experiments",
        json=_build_payload(items[0], "xau xau"),
        headers={"Idempotency-Key": "trunc-equal"},
    ).json()
    _drain(worker)
    r1 = client.get(f"/api/v1/sensitivity-experiments/{exp1['experiment_id']}").json()["result"]
    assert r1["warnings"] == [
        "SENSITIVITY_NOT_CAUSAL",
        "INPUT_TRUNCATED_BASELINE",
        "INPUT_TRUNCATED_VARIANT",
        "MODEL_INPUT_UNCHANGED",
    ]
    # Completed experiment cannot be retried.
    retry_completed = client.post(f"/api/v1/jobs/{exp1['job_id']}/retry")
    assert retry_completed.status_code == 409 and retry_completed.json()["code"] == "JOB_NOT_RETRYABLE"

    # 2. Both truncated + model_input_equal=False -> TOKEN_WINDOW_MAY_CHANGE.
    registry.pair_input_equal_override = False
    exp2 = client.post(
        f"/api/v1/items/{items[0]['id']}/sensitivity-experiments",
        json=_build_payload(items[0], "xau xau"),
        headers={"Idempotency-Key": "trunc-diff"},
    ).json()
    _drain(worker)
    r2 = client.get(f"/api/v1/sensitivity-experiments/{exp2['experiment_id']}").json()["result"]
    assert r2["warnings"] == [
        "SENSITIVITY_NOT_CAUSAL",
        "INPUT_TRUNCATED_BASELINE",
        "INPUT_TRUNCATED_VARIANT",
        "TOKEN_WINDOW_MAY_CHANGE",
    ]

    # 2b. Baseline truncated while variant is NOT truncated (deleting 10 words drops below 128 words).
    drop_needle = " ".join(["xau"] * 5)
    ds_one_trunc = _create_dataset(client, profile="neu", texts=[" ".join(["tot"] * 124 + ["xau"] * 5)])
    one_trunc_item = _items(client, ds_one_trunc["id"])[0]
    registry.pair_input_equal_override = False
    exp_one_trunc = client.post(
        f"/api/v1/items/{one_trunc_item['id']}/sensitivity-experiments",
        json=_build_payload(one_trunc_item, drop_needle),
        headers={"Idempotency-Key": "trunc-baseline-only"},
    ).json()
    _drain(worker)
    r_one_trunc = client.get(f"/api/v1/sensitivity-experiments/{exp_one_trunc['experiment_id']}").json()["result"]
    assert r_one_trunc["warnings"] == [
        "SENSITIVITY_NOT_CAUSAL",
        "INPUT_TRUNCATED_BASELINE",
        "TOKEN_WINDOW_MAY_CHANGE",
    ]

    # 2c. Fresh POST when model unavailable returns 409 MODEL_UNAVAILABLE without leaking rate/temp rows.
    counts_before_unavail = _table_counts(store)
    registry.available = False
    unavail = client.post(
        f"/api/v1/items/{items[1]['id']}/sensitivity-experiments",
        json=_build_payload(items[1], "ngắn"),
        headers={"Idempotency-Key": "create-unavail"},
    )
    assert unavail.status_code == 409 and unavail.json()["code"] == "MODEL_UNAVAILABLE"
    assert _table_counts(store) == counts_before_unavail
    registry.available = True

    # 3. Retry after failed -> tests identity conflict, source revision conflict, quota conflict, then successful recovery.
    registry.pair_fail = True
    exp3 = client.post(
        f"/api/v1/items/{items[1]['id']}/sensitivity-experiments",
        json=_build_payload(items[1], "ngắn"),
        headers={"Idempotency-Key": "retry-guards-3"},
    ).json()
    _drain(worker)
    failed3 = client.get(f"/api/v1/sensitivity-experiments/{exp3['experiment_id']}").json()
    assert failed3["status"] == "failed" and failed3["result"] is None
    assert failed3["error"]["code"] == "INFERENCE_FAILED"
    assert failed3["expires_at"] is not None

    # Model identity change blocks retry -> 409 MODEL_IDENTITY_CHANGED.
    registry.model_version = "v-mismatch"
    assert client.post(f"/api/v1/jobs/{exp3['job_id']}/retry").json()["code"] == "MODEL_IDENTITY_CHANGED"
    registry.model_version = "software-test-only-v1"

    # Global active quota (4) blocks retry -> 429 EXPERIMENT_LIMIT.
    active_blockers = []
    for k in range(2, 5):
        pass
    blocker_items = [items[2], items[3], items[4]]
    extra_ds = _create_dataset(client, profile="neu", texts=["Câu phụ sáu"])
    blocker_items.append(_items(client, extra_ds["id"])[0])
    for idx, b_item in enumerate(blocker_items):
        b = client.post(
            f"/api/v1/items/{b_item['id']}/sensitivity-experiments",
            json=_build_payload(b_item, b_item["text"].split()[0]),
            headers={"Idempotency-Key": f"retry-quota-blk-{idx}"},
        )
        assert b.status_code == 202
        active_blockers.append(b.json()["job_id"])
    retry_429 = client.post(f"/api/v1/jobs/{exp3['job_id']}/retry")
    assert retry_429.status_code == 429 and retry_429.json()["code"] == "EXPERIMENT_LIMIT"
    for b_job in active_blockers:
        assert client.post(f"/api/v1/jobs/{b_job}/cancel").status_code == 200

    # Successful retry clears attempt.error_code, run_items.error, and expires_at before worker runs.
    registry.pair_fail = False
    registry.pair_input_equal_override = None
    retried = client.post(f"/api/v1/jobs/{exp3['job_id']}/retry")
    assert retried.status_code == 200
    assert client.get(f"/api/v1/sensitivity-experiments/{exp3['experiment_id']}").json()["expires_at"] is None
    _drain(worker)
    done3 = client.get(f"/api/v1/sensitivity-experiments/{exp3['experiment_id']}").json()
    assert done3["status"] == "completed" and done3["error"] is None and done3["result"] is not None

    # Failed experiment whose source text was edited -> 409 REVISION_CONFLICT on retry.
    registry.pair_fail = True
    exp4 = client.post(
        f"/api/v1/items/{items[2]['id']}/sensitivity-experiments",
        json=_build_payload(items[2], "ba"),
        headers={"Idempotency-Key": "retry-rev-conflict"},
    ).json()
    _drain(worker)
    client.patch(f"/api/v1/items/{items[2]['id']}/text", json={"text": "Câu ba đã sửa", "expected_revision": 1})
    rev_retry = client.post(f"/api/v1/jobs/{exp4['job_id']}/retry")
    assert rev_retry.status_code == 409 and rev_retry.json()["code"] == "REVISION_CONFLICT"


def test_privacy_context_json_and_error_fields_leak_no_raw_text(env):
    client, store, registry, worker = env
    secret = "BI_MAT_NHAY_CAM_XYZ123"
    ds = _create_dataset(client, profile="neu", texts=[f"Phản hồi chứa {secret} cần bảo mật"])
    item = _items(client, ds["id"])[0]
    exp = client.post(
        f"/api/v1/items/{item['id']}/sensitivity-experiments",
        json=_build_payload(item, secret),
        headers={"Idempotency-Key": "privacy-key"},
    ).json()

    with store.connect() as db:
        raw_ctx = db.execute(
            "SELECT context_json FROM sensitivity_experiments WHERE job_id=?",
            (exp["job_id"],),
        ).fetchone()["context_json"]
    assert secret not in raw_ctx

    registry.pair_fail = RuntimeError(f"Inference crashed on text: {secret}")
    _drain(worker)

    exp_failed = client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").json()
    job_failed = client.get(f"/api/v1/jobs/{exp['job_id']}").json()
    assert exp_failed["status"] == "failed" and exp_failed["result"] is None
    assert secret not in json.dumps(exp_failed["error"])
    assert secret not in json.dumps(job_failed)
    with store.connect() as db:
        ctx_after = db.execute(
            "SELECT context_json FROM sensitivity_experiments WHERE job_id=?",
            (exp["job_id"],),
        ).fetchone()["context_json"]
        ri_errors = [
            r[0]
            for r in db.execute("SELECT error FROM run_items WHERE run_id=?", (job_failed["run_id"],)).fetchall()
            if r[0]
        ]
    assert secret not in ctx_after
    assert all(secret not in msg for msg in ri_errors)
