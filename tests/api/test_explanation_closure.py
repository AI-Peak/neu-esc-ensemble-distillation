"""Negative contracts for canonical prompts and source lifetime (test doubles only)."""
import asyncio
import functools
import json
import time

import httpx
import pytest

from services.api.main import create_app
from services.explanation import ExplanationConfig, ExplanationProvider, ExplanationService, OpenAIExplanationProvider, PROMPT_VERSION
from services.storage.db import profile_for
from services.worker import Worker
from tests.support import TestOnlyRegistry


def async_test(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapped


class GateProvider(ExplanationProvider):
    def __init__(self, gated=True):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not gated:
            self.release.set()
        self.contexts = []

    async def explain(self, context):
        self.contexts.append(context)
        self.started.set()
        await self.release.wait()
        return {"reading": "Kết quả từ provider double.", "caution": "Điểm model chưa hiệu chuẩn."}


async def completed(client, worker, profile="neu", text="Dịch vụ rất tốt luôn"):
    response = await client.post("/api/v1/quick-analysis", json={"profile": profile, "text": text})
    assert response.status_code == 202, response.text
    quick = response.json()
    worker.run_once()
    job = (await client.get(f"/api/v1/jobs/{quick['job_id']}")).json()
    assert job["status"] == "completed"
    return quick, job["result"]


def endpoint(quick):
    return f"/api/v1/quick-analysis/{quick['job_id']}/explanation"


@pytest.mark.parametrize("profile, expected_key", [("neu", "Toxic"), ("uit", "negative")])
@async_test
async def test_prompt_labels_are_canonical_on_provider_boundary(tmp_path, profile, expected_key, record_property):
    registry, provider = TestOnlyRegistry(), GateProvider(gated=False)
    # Explicit winner lets the provider check the mapping, rather than guessing from text.
    def force_winner(pred):
        for task in ("sentiment", "topic"):
            count = len(profile_for(profile)[task])
            winner = 3 if profile == "neu" and task == "sentiment" else 0
            scores = [0.1 / (count - 1)] * count
            scores[winner] = 0.9
            pred[task] = {"label_id": winner, "scores": scores}
    registry.bad = force_winner
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker = Worker(tmp_path, registry)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker, profile=profile)
        response = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
        assert response.status_code == 200, response.text
        context = provider.contexts[0]
        canonical = profile_for(profile)
        assert context["profile_name"] == canonical["name"]
        assert context["prediction"]["sentiment"]["top1"]["key"] == expected_key
        for task in ("sentiment", "topic"):
            distribution = context["prediction"][task]["scores"]
            assert len(distribution) == len(canonical[task])
            for index, (entry, label) in enumerate(zip(distribution, canonical[task])):
                assert {key: entry[key] for key in ("id", "key", "name")} == label
                assert entry["score"] == item["prediction"][task]["scores"][index]
            top1 = context["prediction"][task]["top1"]
            assert top1 == distribution[item["prediction"][task]["label_id"]]
        assert response.json()["prompt_version"] == PROMPT_VERSION == "result-explanation-v2"
        assert "metadata" not in context and "created_at" not in context["prediction"]
        record_property("identity", json.dumps({**quick, "item_id": item["id"], "revision_id": item["revision_id"], "prediction_id": item["prediction"]["id"], "upstream_calls": len(provider.contexts)}))


@pytest.mark.parametrize("change, expected_status", [("revision", 409), ("expiry", 410), ("delete", 404)])
@async_test
async def test_source_rechecked_after_provider_gate(tmp_path, change, expected_status, record_property, monkeypatch):
    registry, provider = TestOnlyRegistry(), GateProvider()
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    connections = set()
    connect = store.connect
    class TrackedConnection:
        def __init__(self):
            self.connection = connect()
            connections.add(self)
        def __getattr__(self, key):
            return getattr(self.connection, key)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            try:
                return self.connection.__exit__(*args)
            finally:
                connections.discard(self)
        def close(self):
            self.connection.close()
            connections.discard(self)
    monkeypatch.setattr(store, "connect", TrackedConnection)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        pending = asyncio.create_task(client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]}))
        await asyncio.wait_for(provider.started.wait(), 2)
        assert not connections, "Provider await must not retain a SQLite connection/transaction"
        # A source write is observed when the network gate is released.
        if change == "revision":
            store.edit_text(item["id"], "Nội dung hiện tại đã thay đổi", item["revision"])
        elif change == "expiry":
            with store.tx() as db:
                db.execute("UPDATE datasets SET expires_at=? WHERE id=?", (time.time() - 1, item["dataset_id"]))
        else:
            with store.tx() as db:
                db.execute("DELETE FROM datasets WHERE id=?", (item["dataset_id"],))
        assert (await client.get("/api/v1/health")).status_code == 200
        provider.release.set()
        response = await asyncio.wait_for(pending, 2)
        assert response.status_code == expected_status, response.text
        assert not connections
        assert len(provider.contexts) == 1
        assert len(app.state.explanation_service._cache) == 0
        again = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
        assert again.status_code == expected_status
        assert len(provider.contexts) == 1
        record_property("gate_observation", json.dumps({"change": change, "job_id": quick["job_id"], "revision_id": item["revision_id"], "prediction_id": item["prediction"]["id"], "status_after_gate": response.status_code, "provider_calls": len(provider.contexts)}))


@pytest.mark.parametrize("change, expected_status", [("revision", 409), ("expiry", 410)])
@async_test
async def test_cached_source_is_validated_before_hit(tmp_path, change, expected_status):
    registry, provider = TestOnlyRegistry(), GateProvider(gated=False)
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        payload = {"source_prediction_id": item["prediction"]["id"]}
        assert (await client.post(endpoint(quick), json=payload)).status_code == 200
        if change == "revision":
            store.edit_text(item["id"], "Khác revision", item["revision"])
        else:
            with store.tx() as db:
                db.execute("UPDATE datasets SET expires_at=? WHERE id=?", (time.time() - 1, item["dataset_id"]))
        assert (await client.post(endpoint(quick), json=payload)).status_code == expected_status
        assert len(provider.contexts) == 1


@async_test
async def test_stale_before_first_call_never_reaches_provider(tmp_path):
    registry, provider = TestOnlyRegistry(), GateProvider(gated=False)
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        store.edit_text(item["id"], "Một revision khác", item["revision"])
        response = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
        assert response.status_code == 409, response.text
        assert not provider.contexts


@async_test
async def test_cache_expiry_cannot_outlive_source(tmp_path):
    registry, provider = TestOnlyRegistry(), GateProvider(gated=False)
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        expires = time.time() + 30
        with store.tx() as db:
            db.execute("UPDATE datasets SET expires_at=? WHERE id=?", (expires, item["dataset_id"]))
        response = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
        assert response.status_code == 200, response.text
        cache = app.state.explanation_service._cache
        assert len(cache) == 1
        _, entry_expires = next(iter(cache._cache.values()))
        assert 0 < entry_expires - time.monotonic() <= expires - time.time() + 0.01


@async_test
async def test_waiting_slot_revalidates_source_and_timeout_releases_queue(tmp_path):
    registry, provider = TestOnlyRegistry(), GateProvider()
    service = ExplanationService(config=ExplanationConfig(timeout_seconds=0.2), provider=provider, max_concurrency=1, max_queue=1)
    app = create_app(tmp_path, registry=registry, explanation_service=service)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        first, first_item = await completed(client, worker)
        second, second_item = await completed(client, worker, text="Phản hồi thứ hai")
        t1 = asyncio.create_task(client.post(endpoint(first), json={"source_prediction_id": first_item["prediction"]["id"]}))
        await asyncio.wait_for(provider.started.wait(), 2)
        t2 = asyncio.create_task(client.post(endpoint(second), json={"source_prediction_id": second_item["prediction"]["id"]}))
        for _ in range(100):
            if service._queued_count == 1:
                break
            await asyncio.sleep(0)
        assert service._queued_count == 1
        with store.tx() as db:
            db.execute("UPDATE datasets SET expires_at=? WHERE id=?", (time.time() - 1, second_item["dataset_id"]))
        provider.release.set()
        r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), 2)
        assert r1.status_code == 200 and r2.status_code == 410, (r1.text, r2.text)
        assert len(provider.contexts) == 1
        # A provider that does not complete times out, then the slot can be reused.
        provider.release.clear()
        third, third_item = await completed(client, worker, text="Phản hồi thứ ba")
        payload = {"source_prediction_id": third_item["prediction"]["id"]}
        timed = await client.post(endpoint(third), json=payload)
        assert timed.status_code == 504
        assert service._queued_count == 0
        provider.release.set()
        retried = await client.post(endpoint(third), json=payload)
        assert retried.status_code == 200, retried.text
        assert service._queued_count == 0


@async_test
async def test_cancel_one_subscriber_keeps_other_and_new_job_is_new_request(tmp_path):
    registry, provider = TestOnlyRegistry(), GateProvider()
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker = Worker(tmp_path, registry)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        payload = {"source_prediction_id": item["prediction"]["id"]}
        first = asyncio.create_task(client.post(endpoint(quick), json=payload))
        await asyncio.wait_for(provider.started.wait(), 2)
        second = asyncio.create_task(client.post(endpoint(quick), json=payload))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        provider.release.set()
        assert (await asyncio.wait_for(second, 2)).status_code == 200
        assert len(provider.contexts) == 1
        other, other_item = await completed(client, worker)
        assert other["job_id"] != quick["job_id"]
        assert (await client.post(endpoint(other), json={"source_prediction_id": other_item["prediction"]["id"]})).status_code == 200
        assert len(provider.contexts) == 2


@pytest.mark.parametrize("upstream, expected", [(401, 502), (403, 502), (429, 429), (500, 502), (504, 504)])
@async_test
async def test_upstream_private_data_never_reaches_api_response_or_logs(tmp_path, upstream, expected, caplog):
    marker = "PRIVATE_UPSTREAM_PAYLOAD_AND_QUERY_KEY"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(upstream, text=marker + request.headers["authorization"]))) as upstream_client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://mock-only.invalid", "synthetic-server-secret", "synthetic-model"), upstream_client)
        registry = TestOnlyRegistry()
        app = create_app(tmp_path, registry=registry, explanation_provider=provider)
        worker = Worker(tmp_path, registry)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            quick, item = await completed(client, worker)
            response = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
            assert response.status_code == expected, response.text
            assert set(response.json()) == {"code", "message"}
            assert marker not in response.text + caplog.text
            assert "synthetic-server-secret" not in response.text + caplog.text
            assert (await client.get("/api/v1/health")).status_code == 200
            assert (await client.get(f"/api/v1/jobs/{quick['job_id']}")).json()["status"] == "completed"


@pytest.mark.parametrize("mutation", ["absent", "short", "oversize", "null", "nonfinite", "range", "label", "schema", "model", "revision", "item", "warnings", "token_count"])
@async_test
async def test_invalid_prediction_never_reaches_explanation_provider(tmp_path, mutation):
    registry, provider = TestOnlyRegistry(), GateProvider(gated=False)
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        with store.tx() as db:
            row = db.execute("SELECT payload FROM predictions WHERE id=?", (item["prediction"]["id"],)).fetchone()
            payload = json.loads(row["payload"])
            if mutation == "absent":
                payload.pop("topic")
            elif mutation == "short":
                payload["topic"]["scores"] = [0.9]
            elif mutation == "oversize":
                payload["topic"]["scores"].append(0)
            elif mutation == "null":
                payload["topic"]["scores"] = None
            elif mutation == "nonfinite":
                # Direct storage validator boundary; this is not JSON-over-network NaN.
                payload["topic"]["scores"][0] = float("nan")
            elif mutation == "range":
                payload["topic"]["scores"][0] = 1.2
            elif mutation == "label":
                payload["topic"]["label_id"] = 15
            elif mutation in ("warnings", "token_count"):
                payload.pop("warnings" if mutation == "warnings" else "token_count_before_truncation")
            else:
                payload[{"schema": "schema_id", "model": "model_id", "revision": "revision_id", "item": "item_id"}[mutation]] = "wrong-identity"
            db.execute("UPDATE predictions SET payload=? WHERE id=?", (json.dumps(payload), item["prediction"]["id"]))
        response = await client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]})
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "INVALID_PREDICTION"
        assert not provider.contexts


@async_test
async def test_known_source_expiry_caps_provider_deadline(tmp_path, monkeypatch):
    registry, provider = TestOnlyRegistry(), GateProvider()
    app = create_app(tmp_path, registry=registry, explanation_provider=provider)
    worker, store = Worker(tmp_path, registry), app.state.store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        quick, item = await completed(client, worker)
        wall = [time.time()]
        expires_at = wall[0] + 0.05
        with store.tx() as db:
            db.execute("UPDATE datasets SET expires_at=? WHERE id=?", (expires_at, item["dataset_id"]))
        # Gate-controlled clock: source validates before provider, expires during await.
        monkeypatch.setattr("services.explanation.time.time", lambda: wall[0])
        pending = asyncio.create_task(client.post(endpoint(quick), json={"source_prediction_id": item["prediction"]["id"]}))
        await asyncio.wait_for(provider.started.wait(), 2)
        wall[0] = expires_at + 1
        response = await asyncio.wait_for(pending, 2)
        assert response.status_code == 410, response.text
        assert len(provider.contexts) == 1 and not provider.release.is_set()
        assert app.state.explanation_service._queued_count == 0
        assert not app.state.explanation_service._inflight
        assert len(app.state.explanation_service._cache) == 0
