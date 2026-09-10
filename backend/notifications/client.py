"""Stage 12 tasks 1/3: the actual HTTP delivery for the two supported
channel types. `post_fn` is the one seam a test overrides (to avoid a
real network call) — it must return an HTTP status code or raise, the
same contract `_default_post` fulfills with httpx.

Redaction: a delivery outcome's `error` never contains the destination
URL, even if the underlying HTTP error message happened to include it
(e.g. a connection error naming the host) — every error string is
scrubbed of the exact url before it's returned, since callers persist
`error` into the delivery log (Stage 12 task 3: "do not log secrets or
full webhook URLs").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

REDACTED_URL = "[redacted webhook url]"


@dataclass(frozen=True)
class DeliveryOutcome:
    success: bool
    status_code: int | None
    error: str | None


def _default_post(url: str, payload: dict, timeout: float) -> int:
    import httpx

    response = httpx.post(url, json=payload, timeout=timeout)
    return response.status_code


def redact(message: str, url: str) -> str:
    if not message:
        return message
    return message.replace(url, REDACTED_URL)


def _post(url: str, payload: dict, post_fn: Callable[[str, dict, float], int] | None, timeout: float) -> DeliveryOutcome:
    poster = post_fn or _default_post
    try:
        status_code = poster(url, payload, timeout)
    except Exception as exc:  # noqa: BLE001 -- any transport failure is a delivery failure, not a crash
        return DeliveryOutcome(success=False, status_code=None, error=redact(str(exc), url))
    if 200 <= status_code < 300:
        return DeliveryOutcome(success=True, status_code=status_code, error=None)
    return DeliveryOutcome(success=False, status_code=status_code, error=f"HTTP {status_code}")


def deliver_webhook(url: str, payload: dict, post_fn: Callable[[str, dict, float], int] | None = None, timeout: float = 5.0) -> DeliveryOutcome:
    return _post(url, payload, post_fn, timeout)


def deliver_slack(url: str, text: str, post_fn: Callable[[str, dict, float], int] | None = None, timeout: float = 5.0) -> DeliveryOutcome:
    return _post(url, {"text": text}, post_fn, timeout)
