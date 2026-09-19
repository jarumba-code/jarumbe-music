"""Health-endpoint tests (``GET /health`` and ``GET /health/db``).

Hermetic: the database is the suite's in-memory SQLite engine; no external
database is contacted.  Covers normal success, controlled DB-failure status,
rate limiting per the health policy, and absence of secret leakage.
"""

from __future__ import annotations

from types import SimpleNamespace as Namespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.database import get_db
from app.main import app

from tests.unit.api_testbed import TEST_SECRET, _headers, _seed_profiles


@pytest.fixture()
def health_client(db_session):
    """TestClient with generous health limits and the SQLite test database."""
    settings = Settings()
    settings.supabase_url = ""
    settings.supabase_jwt_secret = TEST_SECRET
    settings.redis_url = ""
    settings.rate_limit_global_anon_per_minute = 1000
    settings.rate_limit_global_auth_per_minute = 1000
    settings.rate_limit_health_per_minute = 1000

    def _override_get_db():
        yield db_session

    from app.api.deps import get_rate_limit_store
    from app.services.rate_limit import InMemoryRateLimitStore

    store = InMemoryRateLimitStore()
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rate_limit_store] = lambda: store
    try:
        with TestClient(app) as client:
            yield Namespace(client=client, settings=settings, db=db_session)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_rate_limit_store, None)


class TestLivenessEndpoint:
    def test_returns_healthy_payload(self, health_client):
        response = health_client.client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"]
        assert body["environment"]

    def test_exposes_no_secrets(self, health_client):
        text = health_client.client.get("/health").text.lower()
        for marker in ("postgres", "redis://", "jwt", "sqlite", "password"):
            assert marker not in text

    def test_is_rate_limited(self, health_client):
        health_client.settings.rate_limit_health_per_minute = 1
        health_client.settings.rate_limit_global_anon_per_minute = 1000
        assert health_client.client.get("/health").status_code == 200
        response = health_client.client.get("/health")
        assert response.status_code == 429
        assert "Retry-After" in response.headers


class TestDatabaseReadinessEndpoint:
    def test_reports_connected_on_success(self, health_client):
        response = health_client.client.get("/health/db")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "connected"}

    def test_is_a_sync_endpoint_not_async(self):
        """The DB probe must run in a worker thread, not block the loop.

        A synchronous SQLAlchemy call inside an ``async def`` endpoint would
        block the event loop for every in-flight request; ``/health/db`` is
        therefore deliberately declared ``def``.  This pins that contract.
        """
        import inspect

        from app.main import database_health

        assert not inspect.iscoroutinefunction(database_health)

    def test_db_failure_is_a_controlled_503(self, health_client):
        from app.database import get_db as _get_db

        def _failing_db():
            raise OperationalError(
                "SELECT 1", {}, Exception("simulated connection failure")
            )
            yield None  # pragma: no cover - makes this a generator

        app.dependency_overrides[_get_db] = _failing_db
        try:
            response = health_client.client.get("/health/db")
        finally:
            app.dependency_overrides.pop(_get_db, None)
        assert response.status_code == 503
        # Controlled detail — either the route-level probe message or the
        # app-level OperationalError handler; never a raw driver error.
        assert response.json()["detail"] in (
            "Database connection failed",
            "Database temporarily unavailable",
        )
        # The simulated driver message and SQL must not reach the client.
        assert "simulated connection failure" not in response.text
        assert "SELECT 1" not in response.text

    def test_db_failure_leaks_no_connection_string(self, health_client):
        from app.database import get_db as _get_db

        def _failing_db():
            raise OperationalError(
                "SELECT 1",
                {},
                Exception(
                    "could not connect to postgresql://user:secret@host:5432/db"
                ),
            )
            yield None  # pragma: no cover

        app.dependency_overrides[_get_db] = _failing_db
        try:
            response = health_client.client.get("/health/db")
        finally:
            app.dependency_overrides.pop(_get_db, None)
        assert response.status_code == 503
        assert "secret" not in response.text.lower()
        assert "postgresql" not in response.text.lower()
    def test_is_rate_limited(self, health_client):
        health_client.settings.rate_limit_health_per_minute = 1
        health_client.settings.rate_limit_global_anon_per_minute = 1000
        assert health_client.client.get("/health/db").status_code == 200
        assert health_client.client.get("/health/db").status_code == 429
