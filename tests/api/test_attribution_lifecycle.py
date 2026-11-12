import time
import uuid
import json
from fastapi.testclient import TestClient
import pytest

from services.api.main import create_app
from services.storage.db import Store
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def test_setup(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry)
    client = TestClient(app)
    worker = Worker(tmp_path, registry, batch_size=4)
    return client, worker, tmp_path, registry


def test_attribution_lifecycle_and_idempotency(test_setup):
    client, worker, tmp_path, registry = test_setup

    # 1. Create quick analysis
    quick_res = client.post(
        "/api/v1/quick-analysis",
        json={"profile": "neu", "text": "Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm."},
    )
    assert quick_res.status_code == 202
    job_id = quick_res.json()["job_id"]

    # 2. Worker runs quick prediction
    assert worker.run_once() is True
    job_data = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job_data["status"] == "completed"
    pred_id = job_data["result"]["prediction"]["id"]

    # 3. Create attribution job
    attr_res = client.post(
        f"/api/v1/quick-analysis/{job_id}/attribution",
        json={"source_prediction_id": pred_id, "target": {"kind": "polarity_margin"}},
        headers={"Idempotency-Key": "5a897afa-3cf9-462b-a507-ff0a974ad943"},
    )
    assert attr_res.status_code == 202
    attr_id = attr_res.json()["attribution_id"]
    assert attr_res.json()["status"] == "queued"

    # 4. Idempotency test: same key returns same handle
    attr_res_same = client.post(
        f"/api/v1/quick-analysis/{job_id}/attribution",
        json={"source_prediction_id": pred_id, "target": {"kind": "polarity_margin"}},
        headers={"Idempotency-Key": "5a897afa-3cf9-462b-a507-ff0a974ad943"},
    )
    assert attr_res_same.status_code == 202
    assert attr_res_same.json()["attribution_id"] == attr_id

    # 5. Idempotency conflict test: same key with different target returns 409
    attr_res_diff = client.post(
        f"/api/v1/quick-analysis/{job_id}/attribution",
        json={"source_prediction_id": pred_id, "target": {"kind": "label_score", "label_id": 1}},
        headers={"Idempotency-Key": "5a897afa-3cf9-462b-a507-ff0a974ad943"},
    )
    assert attr_res_diff.status_code == 409

    # 6. Worker runs attribution microbatches until completed
    # Run once should execute one microbatch and yield
    ran = worker.run_once()
    assert ran is True

    # Check status mid-flight or continue until done
    for _ in range(50):
        attr_data = client.get(f"/api/v1/attributions/{attr_id}").json()
        if attr_data["status"] == "completed":
            break
        worker.run_once()

    attr_final = client.get(f"/api/v1/attributions/{attr_id}").json()
    assert attr_final["status"] == "completed"
    assert len(attr_final["groups"]) > 0
    assert "baseline_value" in attr_final["aggregate"]
    assert "total_contribution" in attr_final["aggregate"]
    assert "target_output" in attr_final["aggregate"]
    assert attr_final["aggregate"]["additivity_residual"] <= 1e-6

    # 7. Cache hit: calling POST again returns 200 OK with completed payload
    cached_post = client.post(
        f"/api/v1/quick-analysis/{job_id}/attribution",
        json={"source_prediction_id": pred_id, "target": {"kind": "polarity_margin"}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert cached_post.status_code == 200
    assert cached_post.json()["status"] == "completed"
    assert cached_post.json()["attribution_id"] != attr_id
    assert client.post(f"/api/v1/attributions/{attr_id}/cancel").json()["status"] == "completed"


def test_attribution_cancellation(test_setup):
    client, worker, tmp_path, registry = test_setup

    quick_res = client.post(
        "/api/v1/quick-analysis",
        json={"profile": "neu", "text": "Học phí trường khá cao so với mặt bằng chung."},
    )
    job_id = quick_res.json()["job_id"]
    worker.run_once()
    pred_id = client.get(f"/api/v1/jobs/{job_id}").json()["result"]["prediction"]["id"]

    attr_res = client.post(
        f"/api/v1/quick-analysis/{job_id}/attribution",
        json={"source_prediction_id": pred_id, "target": {"kind": "polarity_margin"}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    attr_id = attr_res.json()["attribution_id"]

    cancel_res = client.post(f"/api/v1/attributions/{attr_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    attr_check = client.get(f"/api/v1/attributions/{attr_id}").json()
    assert attr_check["status"] == "cancelled"


def test_attribution_validation_and_origin(test_setup):
    client, worker, tmp_path, registry = test_setup

    # Origin forbidden check
    res = client.post(
        "/api/v1/quick-analysis/non-existent/attribution",
        json={"source_prediction_id": "p1", "target": {"kind": "polarity_margin"}},
        headers={"Origin": "http://evil.com", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert res.status_code == 403

    # Non-existent job
    res_404 = client.post(
        "/api/v1/quick-analysis/non-existent/attribution",
        json={"source_prediction_id": "p1", "target": {"kind": "polarity_margin"}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert res_404.status_code == 404

    # Invalid target (label_score without label_id)
    res_422 = client.post(
        "/api/v1/quick-analysis/some-job/attribution",
        json={"source_prediction_id": "p1", "target": {"kind": "label_score"}},
    )
    assert res_422.status_code == 422
