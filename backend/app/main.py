"""FastAPI application: the routers, and a health check."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api import ask, cea, chats, custom_fields, dashboard, documents, eligibility, families, imports, voice
from app.config import settings
from app.db import get_session
from app.models import Family, Scheme, Soldier
from app.services.error_reporting import init_error_reporting, is_enabled

# Before the app is built, so errors from the very start are reported too.
# Does nothing unless SENTRY_DSN is set.
init_error_reporting()

app = FastAPI(title="Army Passion API", version="0.1.0")

# The screen runs on a different port during development, so the browser
# needs permission to call this API. Set CORS_ORIGINS in .env to change it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports.router)
app.include_router(families.router)
app.include_router(custom_fields.router)
app.include_router(documents.router)
app.include_router(eligibility.router)
app.include_router(voice.router)
app.include_router(dashboard.router)
app.include_router(cea.router)
app.include_router(ask.router)
app.include_router(chats.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.app_env, "timezone": settings.timezone}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    postgis_version = session.scalar(text("SELECT PostGIS_Version()"))
    return {
        "status": "ok",
        "postgis": postgis_version,
        "families": session.scalar(select(func.count()).select_from(Family)),
        "soldiers": session.scalar(select(func.count()).select_from(Soldier)),
        "mock_schemes": session.scalar(select(func.count()).select_from(Scheme)),
    }


class SentryTestError(RuntimeError):
    """Raised on purpose by the test button, to check Sentry receives errors."""


@app.get("/api/debug/sentry")
def sentry_status() -> dict:
    """Whether error reporting is switched on (for the test page)."""
    return {"enabled": is_enabled()}


@app.post("/api/debug/sentry")
def sentry_test() -> dict:
    """Breaks on purpose so the error shows up on the Sentry dashboard."""
    if not is_enabled():
        return {"sent": False, "reason": "Sentry is not switched on here (SENTRY_DSN is empty)."}
    raise SentryTestError("Test error from the backend, sent on purpose from /debug-sentry.")
