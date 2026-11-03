import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import SessionLocal, engine
from app.models import ImportBatch, ImportStatus


@pytest.fixture(autouse=True)
def never_call_a_real_llm(monkeypatch):
    """Tests always use the fake LLM, whatever .env says.

    Without this, running the suite with LLM_PROVIDER=gemini would call the
    real service: slow, costing money, needing internet, and giving slightly
    different answers each run.
    """
    monkeypatch.setattr(settings, "llm_provider", "mock")


@pytest.fixture(scope="session")
def db() -> Session:
    """Read-only look at the seeded development database.

    These tests describe what the mock data generator produces. Once a sheet
    has been imported the database contains rows the generator never made —
    families with no coordinates, soldiers with no weather — so the checks no
    longer apply. Skip with a clear reason rather than failing confusingly.
    """
    session = SessionLocal()
    imported = session.scalar(
        select(func.count())
        .select_from(ImportBatch)
        .where(ImportBatch.status == ImportStatus.imported)
    )
    if imported:
        session.close()
        pytest.skip(
            f"{imported} sheet(s) have been imported, so this database is no "
            "longer just the generated mock data. Run "
            "`python -m seed.generate --reset` to check these again."
        )
    yield session
    session.close()


@pytest.fixture
def tx_db():
    """A session whose writes are always rolled back.

    Import tests create and change families. This makes sure the development
    database is exactly as it was when the test finishes.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
