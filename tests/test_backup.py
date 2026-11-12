import hashlib
from pathlib import Path
import sqlite3
import zipfile

from fastapi.testclient import TestClient
import pytest

from scripts.backup_local import backup, restore
from services.api.main import create_app
from services.storage.db import MIGRATION_1, Store, encode
from services.worker import Worker
from tests.support import TestOnlyRegistry


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utf16_span(text: str, needle: str) -> dict:
    start = text.index(needle)
    end = start + len(needle)
    return {
        "start_utf16": len(text[:start].encode("utf-16-le")) // 2,
        "end_utf16": len(text[:end].encode("utf-16-le")) // 2,
        "text": needle,
    }


def _drain(worker: Worker) -> None:
    for _ in range(200):
        if not worker.run_once():
            return
    raise AssertionError("Worker did not drain")


def _build_v1_database(runtime: Path, *, include_temp: bool = False) -> dict:
    runtime.mkdir(parents=True, exist_ok=True)
    db_path = runtime / "workspace.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    for stmt in MIGRATION_1.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.execute("INSERT INTO schema_migrations VALUES(1, '2026-11-01T00:00:00Z')")

    ds_id = "ds-v1-durable"
    item1_id = "item-v1-1"
    item2_id = "item-v1-2"
    rev1_id = "rev-v1-1"
    rev2_id = "rev-v1-2"
    run_id = "run-v1-1"
    job_id = "job-v1-1"
    pred1_id = "pred-v1-1"
    pred2_id = "pred-v1-2"
    review_id = "revw-v1-1"
    export_id = "exp-v1-snapshot"

    text1 = "Thư viện rộng rãi nhưng điều hòa hơi yếu"
    text2 = "Giảng viên hướng dẫn tận tình và dễ hiểu"

    conn.execute(
        "INSERT INTO datasets VALUES(?,?,?,?,?,?,0,NULL)",
        (ds_id, "Bộ dữ liệu v1 tiếng Việt", "neu", "neu-v1", "2026-11-01T00:00:00Z", "2026-11-01T00:05:00Z"),
    )
    conn.execute("INSERT INTO items VALUES(?,?,1,?)", (item1_id, ds_id, rev1_id))
    conn.execute("INSERT INTO items VALUES(?,?,2,?)", (item2_id, ds_id, rev2_id))
    conn.execute(
        "INSERT INTO revisions VALUES(?,?,1,?,?,?,?)",
        (rev1_id, item1_id, text1, _sha256(text1), encode({"khoa": "CNTT"}), "2026-11-01T00:01:00Z"),
    )
    conn.execute(
        "INSERT INTO revisions VALUES(?,?,1,?,?,?,?)",
        (rev2_id, item2_id, text2, _sha256(text2), encode({"khoa": "KT"}), "2026-11-01T00:01:00Z"),
    )
    conn.execute(
        "INSERT INTO runs VALUES(?,?,?,?,?,?,2,2,0,?)",
        (run_id, ds_id, "neu-v1", "TEST-DOUBLE-NOT-A-MODEL", "software-test-only-v1", "completed", "2026-11-01T00:02:00Z"),
    )
    conn.execute("INSERT INTO run_items VALUES(?,?,?,NULL)", (run_id, item1_id, rev1_id))
    conn.execute("INSERT INTO run_items VALUES(?,?,?,NULL)", (run_id, item2_id, rev2_id))
    conn.execute(
        "INSERT INTO jobs(id,run_id,status,total,completed,failed,cancel_requested,attempt_id,created_at,updated_at,priority) "
        "VALUES(?,?,'completed',2,2,0,0,1,?,?,0)",
        (job_id, run_id, "2026-11-01T00:02:00Z", "2026-11-01T00:02:05Z"),
    )
    for pid, iid, rid in ((pred1_id, item1_id, rev1_id), (pred2_id, item2_id, rev2_id)):
        payload = encode(
            {
                "item_id": iid,
                "revision_id": rid,
                "model_id": "TEST-DOUBLE-NOT-A-MODEL",
                "model_version": "software-test-only-v1",
                "schema_id": "neu-v1",
                "sentiment": {"label_id": 0, "scores": [0.7, 0.1, 0.1, 0.1]},
                "topic": {"label_id": 2, "scores": [0.05] * 2 + [0.55] + [0.05] * 7},
                "token_count_before_truncation": 12,
                "truncated": False,
                "warnings": [],
                "duration_ms": 1.0,
            }
        )
        conn.execute(
            "INSERT INTO predictions VALUES(?,?,?,?,?,?)",
            (pid, run_id, iid, rid, payload, "2026-11-01T00:02:05Z"),
        )
    conn.execute(
        "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (review_id, item1_id, rev1_id, "neu-v1", "sentiment", 1, "corrected", 1, "Ý kiến trung tính từ v1", pred1_id, "2026-11-01T00:03:00Z"),
    )
    v1_csv_bytes = (
        "\ufeffitem_id,source_row,text,effective_sentiment\r\n"
        f"{item1_id},1,{text1},1\r\n"
        f"{item2_id},2,{text2},0\r\n"
    ).encode("utf-8-sig")
    conn.execute(
        "INSERT INTO exports VALUES(?,?,?,?,?,?,2,?)",
        (export_id, ds_id, run_id, "{}", "[]", sqlite3.Binary(v1_csv_bytes), "2026-11-01T00:04:00Z"),
    )

    if include_temp:
        temp_ds = "ds-v1-temp"
        temp_item = "item-v1-temp"
        temp_rev = "rev-v1-temp"
        temp_run = "run-v1-temp"
        temp_job = "job-v1-temp"
        conn.execute(
            "INSERT INTO datasets VALUES(?,?,?,?,?,?,1,1e12)",
            (temp_ds, "Thử nhanh v1", "neu", "neu-v1", "2026-11-01T00:05:00Z", "2026-11-01T00:05:00Z"),
        )
        conn.execute("INSERT INTO items VALUES(?,?,1,?)", (temp_item, temp_ds, temp_rev))
        conn.execute(
            "INSERT INTO revisions VALUES(?,?,1,?,?,?,?)",
            (temp_rev, temp_item, "Câu tạm v1", _sha256("Câu tạm v1"), "{}", "2026-11-01T00:05:00Z"),
        )
        conn.execute(
            "INSERT INTO runs VALUES(?,?,?,?,?,?,1,0,0,?)",
            (temp_run, temp_ds, "neu-v1", "TEST-DOUBLE-NOT-A-MODEL", "software-test-only-v1", "queued", "2026-11-01T00:05:00Z"),
        )
        conn.execute("INSERT INTO run_items VALUES(?,?,?,NULL)", (temp_run, temp_item, temp_rev))
        conn.execute(
            "INSERT INTO jobs(id,run_id,status,total,completed,failed,cancel_requested,attempt_id,created_at,updated_at,priority) "
            "VALUES(?,?,'queued',1,0,0,0,0,?,?,1)",
            (temp_job, temp_run, "2026-11-01T00:05:00Z", "2026-11-01T00:05:00Z"),
        )
        conn.execute("INSERT INTO previews VALUES(?,?,?)", ("prev-v1", "secret preview v1", 1e12))
        conn.execute("INSERT INTO worker_status VALUES(1,'owner-1',1234,'2026-11-01T00:05:00Z',1e12)")
        conn.execute("INSERT INTO idempotency VALUES('idem-ds','dataset','h1',?)", (ds_id,))
        conn.execute("INSERT INTO idempotency VALUES('idem-quick','quick','h2',?)", (temp_job,))

    conn.commit()
    conn.close()
    return {
        "dataset_id": ds_id,
        "item1_id": item1_id,
        "item2_id": item2_id,
        "export_id": export_id,
        "v1_csv_bytes": v1_csv_bytes,
    }


def test_backup_sanitizes_quick_uploads_and_restores_snapshot(tmp_path: Path):
    runtime = tmp_path / "source"
    store = Store(runtime)
    with store.tx() as connection:
        base = ("2026-11-06T00:00:00Z",) * 2
        connection.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?)", ("saved", "Có dấu", "neu", "neu-v1", *base, 0, None))
        connection.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?)", ("quick", "Tạm", "neu", "neu-v1", *base, 1, 1e12))
        connection.execute("INSERT INTO previews VALUES(?,?,?)", ("upload", "secret preview text", 1e12))
    archive = tmp_path / "backup.zip"
    result = backup(runtime, archive)
    assert result["quick_data_excluded"]
    assert not result["models_included"]
    restored = tmp_path / "restored"
    restore(archive, restored)
    connection = sqlite3.connect(restored / "workspace.sqlite3")
    try:
        assert connection.execute("SELECT name FROM datasets").fetchall() == [("Có dấu",)]
        assert connection.execute("SELECT count(*) FROM previews").fetchone()[0] == 0
    finally:
        connection.close()
    with pytest.raises(ValueError, match="mới"):
        restore(archive, restored)
    with pytest.raises(ValueError, match="tồn tại"):
        backup(runtime, archive)
    assert store.datasets()[0]["id"] == "saved"


def test_restore_rejects_archive_paths(tmp_path):
    archive = tmp_path / "malformed.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside", "bad")
        stream.writestr("manifest.json", "{}")
    with pytest.raises(ValueError, match="format"):
        restore(archive, tmp_path / "target")
    assert not (tmp_path / "outside").exists()


def test_backup_restore_v1_migrated_runtime_strips_sensitivity_and_preserves_old_export(tmp_path: Path):
    src_runtime = tmp_path / "src_runtime"
    v1_info = _build_v1_database(src_runtime, include_temp=False)
    ds_id = v1_info["dataset_id"]
    item1_id = v1_info["item1_id"]
    item2_id = v1_info["item2_id"]
    export_id = v1_info["export_id"]
    v1_csv_bytes = v1_info["v1_csv_bytes"]
    secret = "SENS_SECRET_TOKEN_XYZ"

    registry = TestOnlyRegistry()
    src_app = create_app(src_runtime, registry)
    with TestClient(src_app) as client:
        worker = Worker(src_runtime, registry, batch_size=1)
        assert client.get("/api/v1/health").json()["database_version"] == 4
        assert client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes

        # Seed durable items for 10+ sensitivity experiments (kept separate from secret temp strings).
        sens_texts = [f"Phản hồi thử độ nhạy rất tốt số {idx}" for idx in range(11)]
        sens_ds = client.post(
            "/api/v1/datasets",
            json={"name": "Bộ bền thử độ nhạy", "profile": "neu", "items": [{"text": t} for t in sens_texts]},
            headers={"Idempotency-Key": "durable-ds-key"},
        )
        assert sens_ds.status_code == 201
        sens_ds_id = sens_ds.json()["id"]
        sens_items = client.get(f"/api/v1/datasets/{sens_ds_id}/items", params={"page_size": 25}).json()["items"]

        # Seed worker_status, preview, and quick-analysis containing temporary secret text.
        worker.heartbeat()
        preview_resp = client.post(
            "/api/v1/imports/preview",
            files={"file": ("preview.csv", f"text\n{secret} preview\n".encode("utf-8"))},
        )
        assert preview_resp.status_code == 200

        q_done = client.post("/api/v1/quick-analysis", json={"profile": "neu", "text": f"{secret} quick completed"}).json()
        _drain(worker)
        assert client.get(f"/api/v1/jobs/{q_done['job_id']}").json()["status"] == "completed"

        q_queued = client.post("/api/v1/quick-analysis", json={"profile": "neu", "text": f"{secret} quick queued"}).json()
        assert client.get(f"/api/v1/jobs/{q_queued['job_id']}").json()["status"] == "queued"

        q_cancel = client.post("/api/v1/quick-analysis", json={"profile": "neu", "text": f"{secret} quick cancel"}).json()
        assert client.post(f"/api/v1/jobs/{q_cancel['job_id']}/cancel").status_code == 200

        def _create_sens(item_obj: dict, key: str):
            body = {
                "revision_id": item_obj["revision_id"],
                "expected_revision": item_obj["revision"],
                "text_sha256": _sha256(item_obj["text"]),
                "run_id": None,
                "source_prediction_id": None,
                "selection": _utf16_span(item_obj["text"], "rất tốt"),
            }
            return client.post(
                f"/api/v1/items/{item_obj['id']}/sensitivity-experiments",
                json=body,
                headers={"Idempotency-Key": key},
            )

        # Create 10 sensitivity experiments spanning completed, failed, cancelled, and active/queued states
        # while staying under 4 concurrent active experiments so the 11th triggers 429 RATE_LIMIT.
        for idx in range(3):
            r = _create_sens(sens_items[idx], f"sens-done-{idx}")
            assert r.status_code == 202
        _drain(worker)

        registry.pair_fail = RuntimeError(f"Private sensitivity failure: {secret}")
        for idx in range(3, 5):
            r = _create_sens(sens_items[idx], f"sens-fail-{idx}")
            assert r.status_code == 202
        _drain(worker)
        registry.pair_fail = False

        for idx in range(5, 7):
            r = _create_sens(sens_items[idx], f"sens-cancel-{idx}")
            assert r.status_code == 202
            assert client.post(f"/api/v1/jobs/{r.json()['job_id']}/cancel").status_code == 200

        for idx in range(7, 10):
            r = _create_sens(sens_items[idx], f"sens-active-{idx}")
            assert r.status_code == 202
            assert client.get(f"/api/v1/sensitivity-experiments/{r.json()['experiment_id']}").json()["status"] == "queued"

        eleventh = _create_sens(sens_items[10], "sens-rate-11")
        assert eleventh.status_code == 429
        assert eleventh.json()["code"] == "EXPERIMENT_LIMIT"
        assert eleventh.json()["details"]["reason"] == "RATE_LIMIT"

        # Seed a quick idempotency marker as well to ensure non-dataset/run idempotency rows are stripped.
        with src_app.state.store.tx() as db:
            db.execute("INSERT INTO idempotency VALUES('idem-quick-tmp','quick','h-quick',?)", (q_done["job_id"],))

        # New review + append new item on migrated v1 durable dataset must not alter old v1 export bytes.
        rev_resp = client.put(
            f"/api/v1/items/{item2_id}/review",
            json={"task": "topic", "status": "confirmed", "label_id": 2, "expected_revision": 1, "expected_review_revision": 0},
        )
        assert rev_resp.status_code == 200
        add_resp = client.post(
            f"/api/v1/datasets/{ds_id}/items",
            json={"items": [{"text": "Phản hồi mới thêm sau nâng cấp v2"}]},
        )
        assert add_resp.status_code == 201
        assert client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes

    archive = tmp_path / "backup.zip"
    manifest = backup(src_runtime, archive)
    assert manifest["quick_data_excluded"] is True
    assert manifest["models_included"] is False

    dst_runtime = tmp_path / "dst_runtime"
    restore(archive, dst_runtime)

    # Verify restored SQLite database hygiene before app restart.
    dst_conn = sqlite3.connect(dst_runtime / "workspace.sqlite3")
    try:
        assert [r[0] for r in dst_conn.execute("PRAGMA integrity_check").fetchall()] == ["ok"]
        assert dst_conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert dst_conn.execute("SELECT COUNT(*) FROM datasets WHERE temporary=1").fetchone()[0] == 0
        assert dst_conn.execute("SELECT COUNT(*) FROM sensitivity_experiments").fetchone()[0] == 0
        assert dst_conn.execute("SELECT COUNT(*) FROM previews").fetchone()[0] == 0
        assert dst_conn.execute("SELECT COUNT(*) FROM worker_status").fetchone()[0] == 0
        assert dst_conn.execute("SELECT COUNT(*) FROM idempotency WHERE operation IN ('quick', 'sensitivity')").fetchone()[0] == 0
        assert dst_conn.execute("SELECT COUNT(*) FROM sensitivity_rate_limits").fetchone()[0] == 0
        for table_sql in (
            "SELECT text FROM revisions",
            "SELECT error FROM jobs WHERE error IS NOT NULL",
            "SELECT id FROM items",
            "SELECT snapshot, csv_blob FROM exports",
            "SELECT payload FROM predictions",
            "SELECT note FROM reviews",
        ):
            for row in dst_conn.execute(table_sql).fetchall():
                assert secret not in str(row)
    finally:
        dst_conn.close()

    # Simulate app + worker restart on restored runtime.
    dst_registry = TestOnlyRegistry()
    dst_app = create_app(dst_runtime, dst_registry)
    with TestClient(dst_app) as dst_client:
        dst_worker = Worker(dst_runtime, dst_registry, batch_size=1)
        assert dst_client.get("/api/v1/health").json()["database_version"] == 4
        assert len(dst_client.get("/api/v1/datasets").json()) == 2
        assert dst_client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes

        # Verify v1 durable items, reviews, and appended item survived restore intact.
        restored_ds_items = dst_client.get(f"/api/v1/datasets/{ds_id}/items", params={"page_size": 25}).json()["items"]
        assert len(restored_ds_items) == 3
        item1_restored = dst_client.get(f"/api/v1/items/{item1_id}").json()
        item2_restored = dst_client.get(f"/api/v1/items/{item2_id}").json()
        assert item1_restored["effective"]["sentiment"] == 1
        assert item2_restored["reviews"]["topic"]["status"] == "confirmed"

        # Restored runtime must accept a new sensitivity experiment immediately without inheriting 429 rate limit.
        target_item = dst_client.get(f"/api/v1/datasets/{sens_ds_id}/items").json()["items"][10]
        new_exp = dst_client.post(
            f"/api/v1/items/{target_item['id']}/sensitivity-experiments",
            json={
                "revision_id": target_item["revision_id"],
                "expected_revision": target_item["revision"],
                "text_sha256": _sha256(target_item["text"]),
                "run_id": None,
                "source_prediction_id": None,
                "selection": _utf16_span(target_item["text"], "rất tốt"),
            },
            headers={"Idempotency-Key": "restored-fresh-exp"},
        )
        assert new_exp.status_code == 202, new_exp.text
        _drain(dst_worker)
        done_new = dst_client.get(f"/api/v1/sensitivity-experiments/{new_exp.json()['experiment_id']}").json()
        assert done_new["status"] == "completed" and done_new["result"] is not None

        # Append another durable item on restored runtime and re-verify old v1 export bytes stay identical.
        assert (
            dst_client.post(
                f"/api/v1/datasets/{ds_id}/items",
                json={"items": [{"text": "Phản hồi thêm sau khi restore"}]},
            ).status_code
            == 201
        )
        assert dst_client.get(f"/api/v1/exports/{export_id}").content == v1_csv_bytes


def test_backup_works_cleanly_on_unmigrated_v1_database(tmp_path: Path):
    v1_runtime = tmp_path / "v1_unmigrated"
    v1_info = _build_v1_database(v1_runtime, include_temp=True)

    check_conn = sqlite3.connect(v1_runtime / "workspace.sqlite3")
    try:
        tables = {r[0] for r in check_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "sensitivity_experiments" not in tables
        assert "sensitivity_rate_limits" not in tables
        assert [r[0] for r in check_conn.execute("SELECT version FROM schema_migrations").fetchall()] == [1]
    finally:
        check_conn.close()

    archive = tmp_path / "v1_backup.zip"
    manifest = backup(v1_runtime, archive)
    assert manifest["quick_data_excluded"] is True

    restored_v1 = tmp_path / "restored_v1"
    restore(archive, restored_v1)

    restored_conn = sqlite3.connect(restored_v1 / "workspace.sqlite3")
    try:
        assert [r[0] for r in restored_conn.execute("PRAGMA integrity_check").fetchall()] == ["ok"]
        assert restored_conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert restored_conn.execute("SELECT COUNT(*) FROM datasets WHERE temporary=1").fetchone()[0] == 0
        assert restored_conn.execute("SELECT COUNT(*) FROM datasets WHERE temporary=0").fetchone()[0] == 1
        assert restored_conn.execute("SELECT COUNT(*) FROM previews").fetchone()[0] == 0
        assert restored_conn.execute("SELECT COUNT(*) FROM worker_status").fetchone()[0] == 0
        assert restored_conn.execute("SELECT COUNT(*) FROM idempotency WHERE operation='quick'").fetchone()[0] == 0
        assert bytes(
            restored_conn.execute("SELECT csv_blob FROM exports WHERE id=?", (v1_info["export_id"],)).fetchone()[0]
        ) == v1_info["v1_csv_bytes"]
    finally:
        restored_conn.close()

    # Opening Store on restored unmigrated v1 DB upgrades cleanly to v3 preserving durable records.
    upgraded = Store(restored_v1)
    assert upgraded.database_version() == 4
    assert len(upgraded.datasets()) == 1
    assert upgraded.export_bytes(v1_info["export_id"]) == v1_info["v1_csv_bytes"]
