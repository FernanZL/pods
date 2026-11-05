"""Shared test fixtures. CONTRACT FILE.

Every test runs against an isolated temp data dir, an isolated SQLite DB and
fake providers. Nothing here touches the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import db
from app.config import Settings, get_settings
from app.providers import reset_providers


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    for k, v in {
        "DATA_DIR": str(tmp_path / "data"),
        "LLM_PROVIDER": "fake",
        "TRANSCRIBER": "fake",
        "EMBEDDINGS_PROVIDER": "fake",
        "DOWNLOAD_MODE": "fake",
        "OPENAI_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "JOB_CONCURRENCY": "1",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    reset_providers()
    _clear_optional_caches()
    s = get_settings()
    s.ensure_dirs()

    engine = create_engine(f"sqlite:///{s.db_path}", connect_args={"check_same_thread": False})
    db.set_engine(engine)
    SQLModel.metadata.create_all(engine)
    yield s
    engine.dispose()
    db.set_engine(None)  # type: ignore[arg-type]
    get_settings.cache_clear()
    reset_providers()
    _clear_optional_caches()


def _clear_optional_caches() -> None:
    """Clear module-level caches (e.g. the cached vector store) if present."""
    try:
        from app.services import vectorstore

        clear = getattr(vectorstore, "reset_vector_store", None)
        if clear:
            clear()
    except ImportError:
        pass


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    with Session(db.get_engine()) as s:
        yield s


@pytest.fixture
def client(settings: Settings):
    """FastAPI TestClient with lifespan (worker started)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
