"""Shared test fixtures and sample data for Jarumba Music backend tests."""

from __future__ import annotations

import datetime as _dt
import time as _time
from typing import Any

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, Profile
from app.models.external import auth_users
from app.providers.jamendo import JamendoProvider
from app.services.auth import AuthVerificationError, verify_supabase_token


# ---------------------------------------------------------------------------
# Sample Jamendo API responses (based on real v3.0 format)
# ---------------------------------------------------------------------------

SAMPLE_TRACK_RAW = {
    "id": "12345",
    "name": "Afrobeats Fusion",
    "duration": 200,
    "artist_id": "6789",
    "artist_name": "Silver-Stage",
    "artist_idstr": "Silver-Stage",
    "album_name": "Test Album",
    "album_id": "9999",
    "license_ccurl": "http://creativecommons.org/licenses/by-nc-nd/3.0/",
    "position": 1,
    "releasedate": "2020-01-01",
    "album_image": "https://example.com/art1.jpg",
    "audio": "https://example.com/stream1.mp3",
    "audiodownload": "https://example.com/download1.mp3",
    "prourl": "",
    "shorturl": "https://jamen.do/t/12345",
    "shareurl": "https://www.jamendo.com/track/12345",
    "waveform": "not needed",
    "image": "https://example.com/art1.jpg",
    "audiodownload_allowed": True,
    "content_id_free": False,
}

SAMPLE_TRACK_RAW_NO_LICENSE = {
    "id": "67890",
    "name": "No License Track",
    "duration": 180,
    "artist_name": "Unknown Artist",
    "album_name": "",
    "license_ccurl": "",
    "album_image": "https://example.com/art2.jpg",
    "audio": "https://example.com/stream2.mp3",
    "audiodownload": "https://example.com/download2.mp3",
    "audiodownload_allowed": False,
    "shareurl": "https://www.jamendo.com/track/67890",
    "shorturl": "https://jamen.do/t/67890",
    "releasedate": "",
    "image": "https://example.com/art2.jpg",
    "prourl": "",
    "content_id_free": True,
}

SAMPLE_SEARCH_RESPONSE = {
    "headers": {
        "status": "success",
        "code": 0,
        "error_message": "",
        "warnings": "",
        "results_count": 2,
    },
    "results": [SAMPLE_TRACK_RAW, SAMPLE_TRACK_RAW_NO_LICENSE],
}

SAMPLE_GET_TRACK_RESPONSE = {
    "headers": {"status": "success", "code": 0, "error_message": "", "warnings": "", "results_count": 1},
    "results": [SAMPLE_TRACK_RAW],
}

SAMPLE_EMPTY_RESPONSE = {
    "headers": {"status": "success", "code": 0, "error_message": "", "warnings": "", "results_count": 0},
    "results": [],
}

SAMPLE_JAMENDO_ERROR = {
    "headers": {
        "status": "failed",
        "code": 7,
        "error_message": "Jamendo Api Method Not Found Error: This method does not exist",
        "warnings": "The api version you are using (v3.1) does not exist",
        "results_count": 0,
    },
    "results": [],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """FastAPI TestClient."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_http_factory():
    """Factory that creates an httpx.AsyncClient backed by a MockTransport.

    Usage::

        http_client = mock_http_factory(response_dict)
        provider = JamendoProvider(client_id="test", http_client=http_client)
    """
    def _factory(response_data: dict | str, status_code: int = 200, content_type: str = "application/json"):
        if isinstance(response_data, str):
            resp = httpx.Response(status_code, content=response_data.encode(), headers={"content-type": content_type})
        else:
            resp = httpx.Response(status_code, json=response_data)

        def handler(request: httpx.Request) -> httpx.Response:
            return resp

        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport, timeout=5.0)

    return _factory


@pytest.fixture
def success_provider(mock_http_factory):
    """JamendoProvider whose mock transport returns :data:`SAMPLE_SEARCH_RESPONSE`."""
    http_client = mock_http_factory(SAMPLE_SEARCH_RESPONSE)
    return JamendoProvider(client_id="test_client_id", http_client=http_client)


@pytest.fixture
def empty_provider(mock_http_factory):
    """JamendoProvider whose mock transport returns an empty result set."""
    http_client = mock_http_factory(SAMPLE_EMPTY_RESPONSE)
    return JamendoProvider(client_id="test_client_id", http_client=http_client)


@pytest.fixture
def error_provider(mock_http_factory):
    """JamendoProvider whose mock transport returns a Jamendo-level error."""
    http_client = mock_http_factory(SAMPLE_JAMENDO_ERROR)
    return JamendoProvider(client_id="test_client_id", http_client=http_client)


@pytest.fixture
def http_error_provider(mock_http_factory):
    """JamendoProvider whose mock transport returns HTTP 500."""
    http_client = mock_http_factory({"error": "internal"}, status_code=500)
    return JamendoProvider(client_id="test_client_id", http_client=http_client)


@pytest.fixture
def malformed_provider(mock_http_factory):
    """JamendoProvider whose mock transport returns non-JSON content."""
    http_client = mock_http_factory("<html>Bad Gateway</html>", content_type="text/html")
    return JamendoProvider(client_id="test_client_id", http_client=http_client)


@pytest.fixture
def override_provider_dependency():
    """Override the get_jamendo_provider dependency with a provided provider.

    Usage::

        override_provider_dependency.success  # sets up success mock
        response = client.get("/api/v1/music/search?q=test")
    """
    from app.api.routes.music import get_jamendo_provider

    def _override(provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: provider
        yield provider

    yield _override
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Supabase JWT fixtures
# ---------------------------------------------------------------------------


def _build_supabase_token(
    *,
    sub: str,
    secret: str,
    audience: str,
    role: str = "authenticated",
    email: str = "user@example.com",
    exp_offset_seconds: int = 3600,
    now: float | None = None,
) -> str:
    """Build a signed Supabase-style HS256 JWT for use in tests.

    The token includes the claims required by
    :func:`app.services.auth.verify_supabase_token`: ``sub``, ``aud``,
    ``role``, ``email``, ``app_metadata``, ``user_metadata``, and ``exp``.
    """
    now = now if now is not None else _time.time()
    return jwt.encode(
        {
            "sub": sub,
            "aud": audience,
            "role": role,
            "email": email,
            "app_metadata": {},
            "user_metadata": {},
            "exp": int(now + exp_offset_seconds),
            "iat": int(now),
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def jwt_secret() -> str:
    """Shared secret used to sign test JWTs."""
    return "test-jwt-secret-do-not-expose"


@pytest.fixture
def jwt_audience(jwt_secret: str) -> str:
    """Audience value for test JWTs — matches the ``supabase_url`` setting."""
    return "https://example.supabase.co"


@pytest.fixture
def user_id_hex() -> str:
    """A fixed user UUID in string form used across auth tests."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def auth_token_headers(
    client: TestClient,
    jwt_secret: str,
    jwt_audience: str,
    user_id_hex: str,
) -> dict[str, str]:
    """Header dict containing a valid ``Authorization: Bearer <jwt>`` header.

    The underlying JWT is freshly signed for this fixture so it is not expired.
    """
    token = _build_supabase_token(
        sub=user_id_hex,
        secret=jwt_secret,
        audience=jwt_audience,
        exp_offset_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def expired_auth_token_headers(
    client: TestClient,
    jwt_secret: str,
    jwt_audience: str,
    user_id_hex: str,
) -> dict[str, str]:
    """Header dict containing an expired ``Authorization: Bearer <jwt>``."""
    now = _time.time() - 7200  # 2 hours ago
    token = _build_supabase_token(
        sub=user_id_hex,
        secret=jwt_secret,
        audience=jwt_audience,
        exp_offset_seconds=0,
        now=now,
    )
    return {"Authorization": f"Bearer {token}"}



# ---------------------------------------------------------------------------
# Database session fixture for auth/profile tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """A SQLAlchemy session against an in-memory SQLite test database.

    This fixture creates a fresh in-memory database with all tables
    (``profiles`` included) for each test, so tests are hermetic and do not
    touch the development database.

    Fidelity with PostgreSQL
    ------------------------
    The DDL below mirrors the migrated schema closely enough that route
    behaviour is reproduced rather than assumed: foreign keys are *enforced*
    (``PRAGMA foreign_keys=ON``), ``playlist_tracks`` carries both production
    unique constraints — ``(playlist_id, position)`` and ``(playlist_id,
    provider, provider_track_id)`` — plus the ``position >= 0`` check, and
    ``favorites`` keeps its ``(user_id, provider, provider_track_id)``
    uniqueness.  A duplicate insert therefore fails here exactly as it does in
    production, so the routes' 409 / idempotent handling is genuinely
    exercised instead of accidentally passing.

    Known, documented difference: PostgreSQL's ``DEFERRABLE INITIALLY
    DEFERRED`` clause on ``uk_playlist_tracks_playlist_position`` is not
    expressible on a SQLite unique constraint, so a position collision is
    raised at statement time here instead of at COMMIT.  The route's observable
    outcome (409) is identical.
    """
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.profile import Profile  # noqa: F401  ensure model is registered

    # The production schema uses PostgreSQL-specific types (PG_UUID) and
    # constraints (DEFERRABLE foreign keys) that SQLite doesn't support.  For
    # the in-memory test database we create all tables with SQLite-compatible
    # DDL directly, bypassing SQLAlchemy's DDL generation.
    engine = sa.create_engine(
        "sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # SQLite ignores foreign keys unless they are switched on per connection.
    # Production is PostgreSQL with real FK constraints (including
    # ON DELETE CASCADE), so the harness enables enforcement here: a route that
    # depends on the database rejecting a dangling reference is exercised with
    # the same behaviour it gets in production.
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        # auth.users stub (owned by Supabase, not migrated by Jarumba).
        conn.execute(sa.text('CREATE TABLE "auth.users" (id TEXT PRIMARY KEY)'))
        # profiles — references auth.users.id.
        conn.execute(sa.text("""
            CREATE TABLE profiles (
                id TEXT PRIMARY KEY REFERENCES "auth.users"(id) ON DELETE CASCADE,
                display_name VARCHAR(255),
                avatar_url TEXT,
                created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """))
        # favorites — references profiles.id.
        conn.execute(sa.text("""
            CREATE TABLE favorites (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL,
                provider_track_id VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                duration INTEGER,
                artwork_url TEXT,
                license_url TEXT,
                license_name VARCHAR(100),
                created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, provider, provider_track_id)
            )
        """))
        # playlists — references profiles.id.
        conn.execute(sa.text("""
            CREATE TABLE playlists (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                is_public BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """))
        # playlist_tracks — references playlists.id.
        conn.execute(sa.text("""
            CREATE TABLE playlist_tracks (
                id TEXT PRIMARY KEY,
                playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                position INTEGER NOT NULL CHECK (position >= 0),
                provider VARCHAR(50) NOT NULL,
                provider_track_id VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                duration INTEGER,
                artwork_url TEXT,
                license_url TEXT,
                license_name VARCHAR(100),
                added_at DATETIME NOT NULL DEFAULT (datetime('now')),
                CONSTRAINT uk_playlist_tracks_playlist_track
                    UNIQUE (playlist_id, provider, provider_track_id),
                CONSTRAINT uk_playlist_tracks_playlist_position
                    UNIQUE (playlist_id, position)
            )
        """))
        # recently_played — references profiles.id.
        conn.execute(sa.text("""
            CREATE TABLE recently_played (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL,
                provider_track_id VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                artist VARCHAR(255),
                album VARCHAR(255),
                duration INTEGER,
                artwork_url TEXT,
                license_url TEXT,
                license_name VARCHAR(100),
                played_at DATETIME NOT NULL DEFAULT (datetime('now'))
            )
        """))

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    session = Session(bind=engine)

    # Emulate PostgreSQL's ``gen_random_uuid()`` server default: production
    # routes rely on the database to generate primary keys for new resource
    # rows, but SQLite has no such default.  Fill new model instances' ids in
    # before_flush so the harness matches production behavior.  (Test-only —
    # production schema is untouched.)
    import uuid as _uuid

    from app.models.favorite import Favorite  # noqa: F401
    from app.models.playlist import Playlist  # noqa: F401
    from app.models.playlist_track import PlaylistTrack  # noqa: F401
    from app.models.recently_played import RecentlyPlayed  # noqa: F401

    def _autofill_uuids(orm_session, flush_context, instances) -> None:  # noqa: ANN001
        for obj in orm_session.new:
            if isinstance(
                obj, (Favorite, Playlist, PlaylistTrack, RecentlyPlayed)
            ) and not obj.id:
                obj.id = str(_uuid.uuid4())

    event.listen(session, "before_flush", _autofill_uuids)

    try:
        yield session
    finally:
        session.close()
        engine.dispose()



# ---------------------------------------------------------------------------
# Rate-limit isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_rate_limit_store():
    """Give every test its own in-process rate-limit counters.

    Rate limiting now runs *before* JWT verification (so an invalid token
    cannot bypass it), which means tests that intentionally probe 401/404 paths
    consume the anonymous buckets.  A fresh store per test keeps those probes
    independent of each other without weakening any limit: the tests that
    exercise limiting itself install their own store and their own limits
    explicitly.
    """
    from app.api.deps import get_rate_limit_store
    from app.main import app
    from app.services.rate_limit import InMemoryRateLimitStore

    store = InMemoryRateLimitStore()
    app.dependency_overrides[get_rate_limit_store] = lambda: store
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_rate_limit_store, None)

