"""Controlled transport/queue/cache contracts; no external HTTP or model calls."""
import asyncio
import functools
import json
import logging

import httpx
import pytest

from services.explanation import (
    DomainError, ExplanationConfig, ExplanationProvider, ExplanationService,
    MAX_UPSTREAM_RESPONSE_BYTES, OpenAIExplanationProvider, parse_explanation_json,
)


def async_test(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapped


@pytest.mark.parametrize("upstream, expected", [(401, 502), (403, 502), (429, 429), (400, 502), (500, 502), (502, 502), (504, 504)])
@async_test
async def test_raw_error_body_never_reaches_envelope_or_logs(upstream, expected, caplog):
    markers = ["PRIVATE_UPSTREAM_PAYLOAD", "PRIVATE_REQUEST_BODY", "PRIVATE_QUERY_TOKEN", "another-secret-format:%3F"]
    def handler(request):
        return httpx.Response(upstream, text=";".join(markers) + request.headers["authorization"])
    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://test.invalid/v1", "server-only-test-key", "configured-test-model"), client)
        with pytest.raises(DomainError) as caught:
            await provider.explain({"text": "Feedback data"})
    error = caught.value
    assert error.status == expected
    assert error.details is None
    combined = json.dumps({"code": error.code, "message": error.message, "details": error.details}) + caplog.text
    for marker in [*markers, "server-only-test-key"]:
        assert marker not in combined


@pytest.mark.parametrize("kind", ["timeout", "disconnect", "unexpected"])
@async_test
async def test_private_exception_message_is_not_forwarded(kind, caplog):
    marker = "PRIVATE_QUERY_URL_AUTH_TOKEN"
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout(marker + " https://private.invalid/?key=abc", request=request)
        if kind == "disconnect":
            raise httpx.ConnectError(marker, request=request)
        raise RuntimeError(marker)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://test.invalid", "server-key", "test-model"), client)
        with pytest.raises(DomainError) as caught:
            await provider.explain({})
    assert caught.value.status == (504 if kind == "timeout" else 502)
    assert caught.value.details is None
    assert marker not in str(caught.value) + caplog.text


class CountingStream(httpx.AsyncByteStream):
    def __init__(self):
        self.chunks = 0
        self.closed = False

    async def __aiter__(self):
        for _ in range(100):
            self.chunks += 1
            yield b"x" * 8192

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("declared", [False, True])
@async_test
async def test_streaming_size_limit_stops_reading_before_full_body(declared):
    stream = CountingStream()
    def handler(request):
        headers = {"content-length": str(MAX_UPSTREAM_RESPONSE_BYTES + 1)} if declared else {}
        return httpx.Response(200, stream=stream, headers=headers)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://test.invalid", "server-key", "test-model"), client)
        with pytest.raises(DomainError) as caught:
            await provider.explain({})
    assert caught.value.status == 502
    assert "kích thước" in caught.value.message
    assert stream.chunks == (0 if declared else MAX_UPSTREAM_RESPONSE_BYTES // 8192 + 1)
    assert stream.closed


@pytest.mark.parametrize("content", [
    "", "Refusal without JSON", "<html>Gateway failure</html>",
    '{"reading":"ok","caution":"ok","extra":"ignored?"}',
    '{"reading":"<script>alert(1)</script>","caution":"ok"}',
    '{"reading":" ","caution":"ok"}',
    '{"reading":null,"caution":"ok"}',
    'prefix {"reading":"ok","caution":"ok"} suffix',
    json.dumps({"reading": "a" * 2001, "caution": "ok"}),
])
def test_strict_output_rejects_empty_html_refusal_extra_or_oversize(content):
    with pytest.raises(ValueError):
        parse_explanation_json(content)


@pytest.mark.parametrize("response", [
    {"choices": [{"message": {"content": '{"reading":"ok","caution":"ok"}', "refusal": "refused"}}]},
    {"choices": [{"message": {"content": '{"reading":"ok","caution":"ok"}'}, "finish_reason": "length"}]},
    {"choices": []}, {"choices": [None]}, ["wrong object"],
])
@async_test
async def test_bad_upstream_envelope_has_controlled_error(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response))) as client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://test.invalid", "server-key", "test-model"), client)
        with pytest.raises(DomainError) as caught:
            await provider.explain({})
    assert caught.value.code == "EXPLANATION_FAILED" and caught.value.status == 502
    assert caught.value.details is None


@async_test
async def test_provider_config_policy_and_snapshot_are_cache_identities():
    class Provider(ExplanationProvider):
        calls = 0
        async def explain(self, context):
            self.calls += 1
            return {"reading": "ok", "caution": "ok"}
    provider = Provider()
    service = ExplanationService(ExplanationConfig("https://test.invalid", "secret-key-a", "model-a"), provider=provider)
    context = {"revision_id": "r1", "schema_id": "neu-v1", "classifier_model_version": "1", "review_signals": {"policy_hash": "p1"}}
    await service.explain("job", "pred", context)
    await service.explain("job", "pred", context)
    assert provider.calls == 1
    await service.explain("job", "pred", {**context, "revision_id": "r2"})
    await service.explain("job", "pred", {**context, "review_signals": {"policy_hash": "p2"}})
    assert provider.calls == 3
    service.config = ExplanationConfig("https://test.invalid", "secret-key-b", "model-b")
    await service.explain("job", "pred", context)
    assert provider.calls == 4
    assert all(len(key) == 64 and "secret" not in key for key in service._cache._cache)


@async_test
async def test_queue_rejection_and_timeout_do_not_leak_slots():
    class Provider(ExplanationProvider):
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()
        async def explain(self, context):
            self.started.set()
            await self.release.wait()
            return {"reading": "ok", "caution": "ok"}
    provider = Provider()
    service = ExplanationService(ExplanationConfig(timeout_seconds=0.1), provider=provider, max_concurrency=1, max_queue=1)
    active = asyncio.create_task(service.explain("a", "a", {}))
    await provider.started.wait()
    queued = asyncio.create_task(service.explain("b", "b", {}))
    for _ in range(100):
        if service._queued_count == 1:
            break
        await asyncio.sleep(0)
    with pytest.raises(DomainError) as caught:
        await service.explain("c", "c", {})
    assert caught.value.status == 429
    outcomes = await asyncio.gather(active, queued, return_exceptions=True)
    assert all(isinstance(error, DomainError) and error.status == 504 for error in outcomes)
    assert service._queued_count == 0
    assert not service._inflight
    provider.release.set()
    assert (await service.explain("d", "d", {}))["status"] == "completed"


@async_test
async def test_injected_provider_configuration_is_in_cache_identity():
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"reading":"ok","caution":"ok"}'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIExplanationProvider(ExplanationConfig("https://mock.invalid", "key-a", "model-a"), client)
        service = ExplanationService(provider=provider)
        await service.explain("job", "pred", {})
        await service.explain("job", "pred", {})
        assert len(calls) == 1
        provider.config = ExplanationConfig("https://mock.invalid", "key-b", "model-b")
        await service.explain("job", "pred", {})
        assert [call["model"] for call in calls] == ["model-a", "model-b"]


@async_test
async def test_internal_queued_task_cancellation_releases_its_queue_entry():
    class Provider(ExplanationProvider):
        def __init__(self):
            self.started, self.release = asyncio.Event(), asyncio.Event()
        async def explain(self, context):
            self.started.set()
            await self.release.wait()
            return {"reading": "ok", "caution": "ok"}
    provider = Provider()
    service = ExplanationService(provider=provider, max_concurrency=1, max_queue=1)
    first = asyncio.create_task(service.explain("first", "first", {}))
    await provider.started.wait()
    queued = asyncio.create_task(service.explain("queued", "queued", {}))
    for _ in range(100):
        if service._queued_count == 1:
            break
        await asyncio.sleep(0)
    assert service._queued_count == 1
    key = (id(asyncio.get_running_loop()), service._cache_key("queued", "queued", {}))
    service._inflight[key].cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    assert service._queued_count == 0
    provider.release.set()
    assert (await first)["status"] == "completed"
    assert (await service.explain("next", "next", {}))["status"] == "completed"


@async_test
async def test_total_deadline_includes_queue_wait():
    class Provider(ExplanationProvider):
        def __init__(self):
            self.started, self.release = asyncio.Event(), asyncio.Event()
            self.calls = 0
        async def explain(self, context):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return {"reading": "ok", "caution": "ok"}
    provider = Provider()
    service = ExplanationService(ExplanationConfig(timeout_seconds=2), provider=provider, max_concurrency=1)
    active = asyncio.create_task(service.explain("active", "active", {}))
    await provider.started.wait()
    service.config = ExplanationConfig(timeout_seconds=0.05)
    with pytest.raises(DomainError) as caught:
        await service.explain("queued", "queued", {})
    assert caught.value.status == 504
    assert provider.calls == 1 and not active.done()
    assert service._queued_count == 0
    provider.release.set()
    assert (await active)["status"] == "completed"
