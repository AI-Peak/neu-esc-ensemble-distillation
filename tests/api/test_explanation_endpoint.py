from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import pytest
from fastapi.testclient import TestClient
import httpx

from services.api.main import create_app
from services.explanation import ExplanationProvider
from services.worker import Worker
from tests.support import TestOnlyRegistry


class StubExplanationProvider(ExplanationProvider):
    def __init__(
        self,
        reading: str = "Nội dung phản ánh sự bất tiện về thủ tục, phù hợp với nhãn dự đoán.",
        caution: str = "Cần thu thập thêm phản hồi để xác định rõ nguyên nhân gốc rễ.",
        delay: float = 0.0,
    ):
        self.reading = reading
        self.caution = caution
        self.delay = delay
        self.call_count = 0
        self.contexts: list[dict] = []

    async def explain(self, prompt_context: dict) -> dict[str, str]:
        self.call_count += 1
        self.contexts.append(prompt_context)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return {"reading": self.reading, "caution": self.caution}


@pytest.fixture
def test_env(tmp_path):
    registry = TestOnlyRegistry()
    provider = StubExplanationProvider()
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    store = app.state.store
    worker = Worker(tmp_path, registry, batch_size=1)
    with TestClient(app) as client:
        yield client, store, registry, worker, provider, app


def _create_completed_quick_job(client, worker, text="Cổng đăng ký tín chỉ bị chậm và nghẽn mạng.", profile="neu"):
    resp = client.post("/api/v1/quick-analysis", json={"profile": profile, "text": text})
    assert resp.status_code == 202, resp.text
    quick = resp.json()
    worker.run_once()
    job_resp = client.get(f"/api/v1/jobs/{quick['job_id']}")
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["status"] == "completed"
    item = job["result"]
    assert item and item.get("prediction")
    return quick, job, item


# ============================================================================
# 1. Test case 503 when not configured (no provider / env)
# ============================================================================
def test_explanation_endpoint_503_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("FEEDBACK_EXPLANATION_BASE_URL", raising=False)
    monkeypatch.delenv("FEEDBACK_EXPLANATION_API_KEY", raising=False)
    monkeypatch.delenv("FEEDBACK_EXPLANATION_MODEL", raising=False)

    registry = TestOnlyRegistry()
    # Create app without explanation_provider
    app = create_app(tmp_path, registry=registry, explanation_provider=None)
    worker = Worker(tmp_path, registry, batch_size=1)

    with TestClient(app) as client:
        quick, job, item = _create_completed_quick_job(client, worker)
        prediction_id = item["prediction"]["id"]

        resp = client.post(
            f"/api/v1/quick-analysis/{quick['job_id']}/explanation",
            json={"source_prediction_id": prediction_id},
        )
        assert resp.status_code == 503, resp.text
        data = resp.json()
        assert data["code"] == "EXPLANATION_UNAVAILABLE"
        assert "chưa được cấu hình" in data["message"]


# ============================================================================
# 2. Test case 200 success with schema Section 6.1
# ============================================================================
def test_explanation_endpoint_200_success_schema(test_env):
    client, store, registry, worker, provider, app = test_env
    quick, job, item = _create_completed_quick_job(client, worker, profile="neu")
    pred = item["prediction"]

    resp = client.post(
        f"/api/v1/quick-analysis/{quick['job_id']}/explanation",
        json={"source_prediction_id": pred["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Schema Section 6.1 assertions:
    assert data["status"] == "completed"
    assert data["job_id"] == quick["job_id"]
    assert data["run_id"] == quick["run_id"]
    assert data["item_id"] == item["id"]
    assert data["revision_id"] == (item.get("revision_id") or str(item.get("revision", "")))
    assert data["source_prediction_id"] == pred["id"]
    assert data["profile_id"] == "neu"
    assert data["schema_id"] == "neu-v1"
    assert data["classifier_model_id"] == pred["model_id"]
    assert "classifier_model_version" in data
    assert data["prompt_version"] == "result-explanation-v2"
    assert data["reading"] == provider.reading
    assert data["caution"] == provider.caution


# ============================================================================
# 3. Test case 409 when job not ready (JOB_NOT_READY)
# ============================================================================
def test_explanation_endpoint_409_job_not_ready(test_env):
    client, store, registry, worker, provider, app = test_env
    resp = client.post(
        "/api/v1/quick-analysis",
        json={"profile": "neu", "text": "Học phí học kỳ này cao quá."},
    )
    assert resp.status_code == 202
    quick = resp.json()

    # Worker has NOT run yet; status is queued
    job_status = client.get(f"/api/v1/jobs/{quick['job_id']}").json()
    assert job_status["status"] == "queued"

    exp_resp = client.post(
        f"/api/v1/quick-analysis/{quick['job_id']}/explanation",
        json={"source_prediction_id": "dummy-pred-id"},
    )
    assert exp_resp.status_code == 409, exp_resp.text
    data = exp_resp.json()
    assert data["code"] == "JOB_NOT_READY"
    assert "chưa hoàn thành" in data["message"]


# ============================================================================
# 4. Test case 409 when source_prediction_id mismatch (SOURCE_CONFLICT)
# ============================================================================
def test_explanation_endpoint_409_source_conflict(test_env):
    client, store, registry, worker, provider, app = test_env
    quick, job, item = _create_completed_quick_job(client, worker)
    actual_pred_id = item["prediction"]["id"]
    wrong_pred_id = f"wrong-id-{actual_pred_id}"

    resp = client.post(
        f"/api/v1/quick-analysis/{quick['job_id']}/explanation",
        json={"source_prediction_id": wrong_pred_id},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["code"] == "SOURCE_CONFLICT"
    assert "không khớp" in data["message"]


# ============================================================================
# 5. Test case 410 when temporary dataset expired (JOB_EXPIRED)
# ============================================================================
def test_explanation_endpoint_410_job_expired(test_env):
    client, store, registry, worker, provider, app = test_env
    quick, job, item = _create_completed_quick_job(client, worker)
    pred_id = item["prediction"]["id"]

    # Manually expire the temporary dataset without triggering cleanup deletion
    with store.tx() as db:
        db.execute(
            "UPDATE datasets SET expires_at=? WHERE temporary=1",
            (time.time() - 3600,),
        )

    resp = client.post(
        f"/api/v1/quick-analysis/{quick['job_id']}/explanation",
        json={"source_prediction_id": pred_id},
    )
    assert resp.status_code == 410, resp.text
    data = resp.json()
    assert data["code"] == "JOB_EXPIRED"
    assert "hết hạn" in data["message"]


# ============================================================================
# 6. Test case Origin check (FORBIDDEN_ORIGIN, same host, no origin)
# ============================================================================
def test_explanation_endpoint_origin_check(test_env):
    client, store, registry, worker, provider, app = test_env
    quick, job, item = _create_completed_quick_job(client, worker)
    pred_id = item["prediction"]["id"]

    url = f"/api/v1/quick-analysis/{quick['job_id']}/explanation"
    payload = {"source_prediction_id": pred_id}

    # 1. No Origin header -> allowed (for test clients and non-browser callers)
    res_no_origin = client.post(url, json=payload)
    assert res_no_origin.status_code == 200

    # 2. Origin same host (testserver) -> allowed
    res_same_origin = client.post(url, json=payload, headers={"Origin": "http://testserver"})
    assert res_same_origin.status_code == 200

    # 3. Origin localhost vs 127.0.0.1 -> allowed
    res_local = client.post(
        url,
        json=payload,
        headers={"Origin": "http://localhost:8765", "Host": "127.0.0.1:8765"},
    )
    assert res_local.status_code == 200

    # 4. Origin from external / malicious domain -> 403 FORBIDDEN_ORIGIN
    res_external = client.post(
        url,
        json=payload,
        headers={"Origin": "https://malicious-site.example.com"},
    )
    assert res_external.status_code == 403, res_external.text
    data = res_external.json()
    assert data["code"] == "FORBIDDEN_ORIGIN"
    assert "không được phép" in data["message"]


# ============================================================================
# 7. Test case Deduplication and Caching
# ============================================================================
def test_explanation_endpoint_deduplication_and_caching(tmp_path):
    async def _run():
        registry = TestOnlyRegistry()
        provider = StubExplanationProvider(delay=0.05)
        app = create_app(tmp_path, registry=registry, explanation_provider=provider)
        worker = Worker(tmp_path, registry, batch_size=1)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/api/v1/quick-analysis",
                json={"profile": "neu", "text": "Đăng ký môn học quá khó khăn."},
            )
            assert resp.status_code == 202
            quick = resp.json()

            worker.run_once()

            job_resp = await client.get(f"/api/v1/jobs/{quick['job_id']}")
            assert job_resp.status_code == 200
            job = job_resp.json()
            pred_id = job["result"]["prediction"]["id"]

            url = f"/api/v1/quick-analysis/{quick['job_id']}/explanation"
            payload = {"source_prediction_id": pred_id}

            # Send 2 concurrent requests on the same event loop
            res1, res2 = await asyncio.gather(
                client.post(url, json=payload),
                client.post(url, json=payload),
            )

            assert res1.status_code == 200, res1.text
            assert res2.status_code == 200, res2.text
            data1 = res1.json()
            data2 = res2.json()
            assert data1["reading"] == data2["reading"]
            assert data1["source_prediction_id"] == pred_id

            # Deduplication: in-flight request coalesced -> provider called only once
            assert provider.call_count == 1

            # 3rd request after completion -> cache hit
            res3 = await client.post(url, json=payload)
            assert res3.status_code == 200, res3.text
            data3 = res3.json()
            assert data3["reading"] == data1["reading"]

            # Provider call count remains 1
            assert provider.call_count == 1

    asyncio.run(_run())
