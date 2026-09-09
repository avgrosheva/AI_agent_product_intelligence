"""Stage 9 task 7: Langfuse HTTP client tests — pagination, retries on
transient failures, immediate failure on non-transient errors, and secret
redaction. No real network access: a small in-memory FakeTransport stands
in for backend.connectors.langfuse.client.HttpxTransport."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.connectors.langfuse.client import LangfuseAPIError, LangfuseClient
from backend.connectors.langfuse.config import LangfuseConfigError, LangfuseConnectionConfig


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text or str(body)

    def json(self) -> dict:
        return self._body


class FakeTransport:
    """Queues one canned response per `.get()` call, in order, and
    records every call's url/params for assertions."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params), "auth": auth})
        return self._responses.pop(0)


CONFIG = LangfuseConnectionConfig(public_key="pub_test", secret_key="sk_supersecret", host="https://fake.langfuse.test")


def _client(responses: list[FakeResponse], **kwargs) -> tuple[LangfuseClient, FakeTransport]:
    transport = FakeTransport(responses)
    client = LangfuseClient(config=CONFIG, transport=transport, sleep_fn=lambda s: None, **kwargs)
    return client, transport


def test_fetch_traces_paginates_across_all_pages():
    responses = [
        FakeResponse(200, {"data": [{"id": "t1"}, {"id": "t2"}], "meta": {"page": 1, "totalPages": 2}}),
        FakeResponse(200, {"data": [{"id": "t3"}], "meta": {"page": 2, "totalPages": 2}}),
    ]
    client, transport = _client(responses)
    traces = list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert [t["id"] for t in traces] == ["t1", "t2", "t3"]
    assert [c["params"]["page"] for c in transport.calls] == [1, 2]


def test_fetch_traces_single_page_stops_after_one_call():
    responses = [FakeResponse(200, {"data": [{"id": "t1"}], "meta": {"page": 1, "totalPages": 1}})]
    client, transport = _client(responses)
    traces = list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert len(traces) == 1
    assert len(transport.calls) == 1


def test_fetch_trace_detail_calls_the_per_trace_endpoint():
    responses = [FakeResponse(200, {"id": "t1", "observations": []})]
    client, transport = _client(responses)
    detail = client.fetch_trace_detail("t1")
    assert detail == {"id": "t1", "observations": []}
    assert transport.calls[0]["url"].endswith("/api/public/traces/t1")


def test_retries_on_500_then_succeeds():
    responses = [
        FakeResponse(500, text="internal error"),
        FakeResponse(200, {"data": [], "meta": {"page": 1, "totalPages": 1}}),
    ]
    client, transport = _client(responses)
    traces = list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert traces == []
    assert len(transport.calls) == 2


def test_retries_on_429_then_succeeds():
    responses = [
        FakeResponse(429, text="rate limited"),
        FakeResponse(200, {"data": [], "meta": {"page": 1, "totalPages": 1}}),
    ]
    client, transport = _client(responses)
    list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert len(transport.calls) == 2


def test_exhausts_retries_and_raises_with_status_code():
    responses = [FakeResponse(503, text="down") for _ in range(3)]
    client, transport = _client(responses, max_retries=3)
    with pytest.raises(LangfuseAPIError) as exc_info:
        list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert exc_info.value.status_code == 503
    assert len(transport.calls) == 3


def test_non_retryable_4xx_raises_immediately_without_retrying():
    responses = [FakeResponse(401, text="unauthorized")]
    client, transport = _client(responses)
    with pytest.raises(LangfuseAPIError) as exc_info:
        list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert exc_info.value.status_code == 401
    assert len(transport.calls) == 1


def test_auth_tuple_carries_public_and_secret_key():
    responses = [FakeResponse(200, {"data": [], "meta": {"page": 1, "totalPages": 1}})]
    client, transport = _client(responses)
    list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert transport.calls[0]["auth"] == ("pub_test", "sk_supersecret")


def test_config_repr_and_str_redact_the_secret_key():
    assert "sk_supersecret" not in repr(CONFIG)
    assert "sk_supersecret" not in str(CONFIG)
    assert "pub_test" in repr(CONFIG)  # the public key isn't secret


def test_langfuse_api_error_message_never_includes_the_secret_key():
    responses = [FakeResponse(401, text="unauthorized")]
    client, _ = _client(responses)
    with pytest.raises(LangfuseAPIError) as exc_info:
        list(client.fetch_traces(datetime(2026, 1, 1), datetime(2026, 1, 2)))
    assert "sk_supersecret" not in str(exc_info.value)


def test_from_env_requires_both_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    with pytest.raises(LangfuseConfigError):
        LangfuseConnectionConfig.from_env()


def test_from_env_reads_keys_and_default_host(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub_env")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_env")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    config = LangfuseConnectionConfig.from_env()
    assert config.public_key == "pub_env"
    assert config.secret_key == "sk_env"
    assert config.host == "https://cloud.langfuse.com"


def test_from_env_host_override_takes_priority_over_env_var(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub_env")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_env")
    monkeypatch.setenv("LANGFUSE_HOST", "https://env-host.example.com")
    config = LangfuseConnectionConfig.from_env(host_override="https://explicit-host.example.com")
    assert config.host == "https://explicit-host.example.com"
