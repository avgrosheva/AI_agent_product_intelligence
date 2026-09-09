"""Langfuse HTTP client (Stage 9 task 1). Talks to Langfuse's public API:
`GET /api/public/traces` for the time-ranged, paginated list of trace
summaries, and `GET /api/public/traces/{id}` for one trace's full detail
(including its nested `observations` — spans, generations, tool/error
events). Authenticates with HTTP Basic Auth, public key as username,
secret key as password, exactly as Langfuse's own API expects.

The HTTP transport is injected (`transport`) rather than hardcoded to a
global `httpx.Client`, so tests exercise pagination, retries, and error
handling against a small in-memory fake instead of a real network call or
a mocking library — the fake only needs a `.get(url, params=..., auth=...,
timeout=...)` method returning an object with `.status_code`, `.json()`,
and `.text`. `HttpxTransport` (the default, used outside tests) is the
one piece of this module a test never has to construct.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from backend.connectors.langfuse.config import LangfuseConnectionConfig


class LangfuseAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Langfuse API error {status_code}: {message}")


class HTTPResponse(Protocol):
    status_code: int

    def json(self) -> dict: ...

    @property
    def text(self) -> str: ...


class HTTPTransport(Protocol):
    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> HTTPResponse: ...


class HttpxTransport:
    """The real transport, backed by httpx. Never constructed by a test —
    tests inject their own HTTPTransport fake instead."""

    def __init__(self) -> None:
        import httpx

        self._client = httpx.Client()

    def get(self, url: str, *, params: dict, auth: tuple[str, str], timeout: float) -> HTTPResponse:
        return self._client.get(url, params=params, auth=auth, timeout=timeout)


def _default_transport() -> HTTPTransport:
    return HttpxTransport()


@dataclass
class LangfuseClient:
    config: LangfuseConnectionConfig
    transport: HTTPTransport = field(default_factory=_default_transport)
    max_retries: int = 3
    sleep_fn: Callable[[float], None] = time.sleep

    def _auth(self) -> tuple[str, str]:
        return (self.config.public_key, self.config.secret_key)

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.config.host.rstrip('/')}{path}"
        last_error: LangfuseAPIError | None = None
        for attempt in range(self.max_retries):
            response = self.transport.get(url, params=params, auth=self._auth(), timeout=10.0)
            if response.status_code < 300:
                return response.json()
            if response.status_code == 429 or response.status_code >= 500:
                last_error = LangfuseAPIError(response.status_code, response.text)
                if attempt < self.max_retries - 1:
                    self.sleep_fn(0.5 * (attempt + 1))
                continue
            # Any other 4xx (auth failure, bad request, ...) is not
            # transient — retrying it would just fail the same way.
            raise LangfuseAPIError(response.status_code, response.text)
        assert last_error is not None
        raise last_error

    def fetch_traces(self, start: datetime, end: datetime, *, page_size: int = 100) -> Iterator[dict]:
        """Yields raw trace summary dicts across every page in [start, end]."""
        page = 1
        while True:
            body = self._get(
                "/api/public/traces",
                {"fromTimestamp": start.isoformat(), "toTimestamp": end.isoformat(), "page": page, "limit": page_size},
            )
            for trace in body.get("data", []):
                yield trace
            meta = body.get("meta", {})
            if page >= meta.get("totalPages", page):
                break
            page += 1

    def fetch_trace_detail(self, trace_id: str) -> dict:
        """Full trace detail, including its nested `observations` list —
        the list endpoint above only returns summaries."""
        return self._get(f"/api/public/traces/{trace_id}", {})
