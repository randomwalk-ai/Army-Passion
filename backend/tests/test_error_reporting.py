"""Error reporting to Sentry: off by default, and never carries personal data."""

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.config import settings
from app.main import ALLOWED_ORIGINS, app
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


ORIGIN = sorted(ALLOWED_ORIGINS)[0]


@pytest.fixture
def crash_route():
    """A route that crashes, for checking the reply to an unplanned error."""
    path = "/api/test-only/crash"
    if not any(getattr(r, "path", None) == path for r in app.router.routes):
        def crash():
            raise ValueError("an unplanned crash")
        app.add_api_route(path, crash, methods=["GET"])
    return path


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
    response = client.post(
        "/api/debug/sentry?name=Paramjit",
        json={"phone": "+919876543210"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 500
    # The screens can read the reply, so they say "something went wrong",
    # not "could not reach the server".
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "It has been reported" in response.json()["detail"]
    sentry_sdk.flush()

    assert len(capture.events) == 1, "the error should be reported exactly once"
    event = capture.events[-1]
    assert event["exception"]["values"][-1]["type"] == "SentryTestError"
    text = str(event)
    assert "Paramjit" not in text and "+919876543210" not in text
    assert "user" not in event
    frames = event["exception"]["values"][-1]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)


def test_an_unplanned_crash_gets_a_readable_reply(crash_route, monkeypatch, sentry_off_afterwards):
    """Even with Sentry off, a crash reply carries the CORS label and a plain message."""
    monkeypatch.setattr(settings, "sentry_dsn", "")
    init_error_reporting()
    client = TestClient(app, raise_server_exceptions=False)

    allowed = client.get(crash_route, headers={"Origin": ORIGIN})
    assert allowed.status_code == 500
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.json() == {"detail": "Something went wrong on the server. It has been reported."}
    # Nothing about the crash itself (a value, a name) is shown to the screen.
    assert "unplanned" not in allowed.text

    # A website we do not allow gets the reply without the label.
    other = client.get(crash_route, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
