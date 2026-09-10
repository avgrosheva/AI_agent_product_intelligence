"""Stage 12 tasks 1/3: notification delivery client — webhook/Slack
success and failure, and URL redaction in error messages. Pure, no real
network access: `post_fn` stands in for the real HTTP call."""

from __future__ import annotations

from backend.notifications.client import deliver_slack, deliver_webhook, redact

URL = "https://hooks.slack.com/services/T00/B00/supersecrettoken"


def test_webhook_success_reports_delivered():
    outcome = deliver_webhook(URL, {"a": 1}, post_fn=lambda url, payload, timeout: 200)
    assert outcome.success is True
    assert outcome.status_code == 200
    assert outcome.error is None


def test_webhook_non_2xx_status_is_a_failure():
    outcome = deliver_webhook(URL, {"a": 1}, post_fn=lambda url, payload, timeout: 500)
    assert outcome.success is False
    assert outcome.status_code == 500
    assert outcome.error == "HTTP 500"


def test_slack_payload_shape_is_text_only():
    captured = {}

    def fake_post(url, payload, timeout):
        captured["payload"] = payload
        return 200

    outcome = deliver_slack(URL, "ROLLBACK for exp-1", post_fn=fake_post)
    assert outcome.success is True
    assert captured["payload"] == {"text": "ROLLBACK for exp-1"}


def test_network_exception_is_caught_and_redacted():
    def raising_post(url, payload, timeout):
        raise ConnectionError(f"could not connect to {url}")

    outcome = deliver_webhook(URL, {}, post_fn=raising_post)
    assert outcome.success is False
    assert outcome.status_code is None
    assert URL not in outcome.error
    assert "[redacted webhook url]" in outcome.error


def test_redact_helper_replaces_exact_url_only():
    message = f"connection to {URL} timed out"
    assert redact(message, URL) == "connection to [redacted webhook url] timed out"
    assert redact("unrelated message", URL) == "unrelated message"
