"""Error reporting to Sentry: off by default, and never carries personal data."""

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.config import settings
from app.main import app
from app.services import error_reporting
from app.services.error_reporting import init_error_reporting, scrub


class Capture(Transport):
    """Keeps events in a list instead of sending them to sentry.io."""

    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@pytest.fixture
def sentry_off_afterwards():
    yield
    sentry_sdk.init()  # no DSN: switches the client off again


def test_off_without_a_dsn(monkeypatch, sentry_off_afterwards):
    monkeypatch.setattr(settings, "sentry_dsn", "")
    assert init_error_reporting() is False
    assert TestClient(app).get("/api/debug/sentry").json() == {"enabled": False}
    reply = TestClient(app).post("/api/debug/sentry").json()
    assert reply["sent"] is False


def test_scrub_removes_personal_parts():
    event = {
        "request": {
            "url": "https://api.example.com/api/families?q=Paramjit+Kaur",
            "query_string": "q=Paramjit+Kaur",
            "data": {"primary_phone": "+919876543210"},
            "cookies": {"session": "x"},
            "headers": {"User-Agent": "Chrome", "Authorization": "secret", "X-Forwarded-For": "1.2.3.4"},
        },
        "user": {"ip_address": "1.2.3.4"},
        "breadcrumbs": {"values": [{"data": {"url": "https://x/api/ask?q=meena"}}]},
    }
    cleaned = scrub(event)
    request = cleaned["request"]
    assert request["url"] == "https://api.example.com/api/families"
    assert "data" not in request and "cookies" not in request and "query_string" not in request
    assert request["headers"] == {"User-Agent": "Chrome"}
    assert "user" not in cleaned
    assert cleaned["breadcrumbs"]["values"][0]["data"]["url"] == "https://x/api/ask"


def test_a_real_error_reaches_sentry_without_personal_data(monkeypatch, sentry_off_afterwards):
    capture = Capture()
    monkeypatch.setattr(settings, "sentry_dsn", "https://public@example.invalid/1")
    real_init = sentry_sdk.init
    monkeypatch.setattr(
        error_reporting.sentry_sdk, "init", lambda **kw: real_init(transport=capture, **kw)
    )
    assert init_error_reporting() is True

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/debug/sentry").json() == {"enabled": True}
    response = client.post("/api/debug/sentry?name=Paramjit", json={"phone": "+919876543210"})
    assert response.status_code == 500
    sentry_sdk.flush()

    assert capture.events, "the test error should have been captured"
    event = capture.events[-1]
    assert event["exception"]["values"][-1]["type"] == "SentryTestError"
    text = str(event)
    assert "Paramjit" not in text and "+919876543210" not in text
    assert "user" not in event
    frames = event["exception"]["values"][-1]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)
