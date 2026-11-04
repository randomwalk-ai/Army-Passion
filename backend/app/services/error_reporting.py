"""Sending errors to Sentry, so they can be looked at on sentry.io.

Switched on only when SENTRY_DSN is set (on Render). On a developer's
computer it is empty, so nothing is ever sent from there.

PRIVACY: an error report must never carry a family's details. So:
- no request bodies (an Excel row, a form being saved), no cookies, no IP
  addresses, no logged-in user (send_default_pii=False, bodies "never");
- no local variables from the code (they can hold a family's record);
- no query strings (a search like ?q=Paramjit Kaur), stripped in `scrub`;
- no SQL parameters (only the shape of a query, never its values).
What is left: the type of error, its message, where in the code it happened,
which address was called, and when.
"""

from __future__ import annotations

import os
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import settings

# Request headers that are safe and useful; every other header is dropped.
SAFE_HEADERS = {"user-agent", "referer", "content-type", "accept"}


def scrub(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Last check before an event leaves this machine: remove anything personal."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in SAFE_HEADERS}
    event.pop("user", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values", []) or []:
        data = crumb.get("data")
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            data["url"] = data["url"].split("?", 1)[0]
    return event


def init_error_reporting() -> bool:
    """Start Sentry if a DSN is configured. Returns whether it was started."""
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment or settings.app_env,
        # Render sets this to the commit being run, so each error shows which version.
        release=os.environ.get("RENDER_GIT_COMMIT") or None,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        # Errors only; no performance tracing (fewer events, nothing extra sent).
        traces_sample_rate=0.0,
        before_send=scrub,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    return True


def is_enabled() -> bool:
    return sentry_sdk.get_client().is_active()
