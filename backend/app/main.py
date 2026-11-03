"""FastAPI application: the routers, and a health check."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api import cea, custom_fields, dashboard, documents, families, imports, voice
from app.config import settings
from app.db import get_session
from app.models import Family, Scheme, Soldier

app = FastAPI(title="Army Passion API", version="0.1.0")

# The screen runs on a different port during development, so the browser
# needs permission to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports.router)
app.include_router(families.router)
app.include_router(custom_fields.router)
app.include_router(documents.router)
app.include_router(voice.router)
app.include_router(dashboard.router)
app.include_router(cea.router)


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
