import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import configure_sqlite
from app.main import app


@pytest.fixture()
def test_engine(monkeypatch):
    """Opt-in live PostgreSQL; every test owns a disposable, isolated schema."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    url = os.environ.get("TEST_POSTGRES_URL", "sqlite://")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    if url == "sqlite://":
        engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        configure_sqlite(engine)
        cleanup_engine = None
    else:
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").startswith("test_"):
            raise ValueError("TEST_POSTGRES_URL must select a PostgreSQL database named test_*")
        schema = "test_" + uuid4().hex
        cleanup_engine = create_engine(url)
        with cleanup_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url)

        @event.listens_for(engine, "connect")
        def set_search_path(connection, _record):
            # SET must survive application rollbacks, so establish it outside a transaction.
            previous = connection.autocommit
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f'SET search_path TO "{schema}"')
            finally:
                connection.autocommit = previous
    try:
        yield engine
    finally:
        engine.dispose()
        if cleanup_engine is not None:
            with cleanup_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            cleanup_engine.dispose()
        get_settings.cache_clear()


@pytest.fixture()
def db_session(test_engine):
    engine = test_engine
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
