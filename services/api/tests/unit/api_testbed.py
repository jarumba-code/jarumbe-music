"""Shared testbed for API-resource and rate-limit tests.

Builds a TestClient wired to:
* an in-memory SQLite database (via the ``db_session`` fixture's engine),
* a fresh in-process rate-limit store per test,
* legacy HS256 settings (deterministic, no network),
* pre-seeded profiles for two users (A and B) with valid Bearer headers.
"""

from __future__ import annotations

import time
from types import SimpleNamespace as Namespace
from typing import Any

import jwt as pyjwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.main import app

TEST_SECRET = "test-jwt-secret-do-not-expose"

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


def _token(user_id: str, *, exp_offset: int = 3600) -> str:
    now = time.time()
    return pyjwt.encode(
        {
            "sub": user_id,
            "aud": "https://example.supabase.co",
            "role": "authenticated",
            "email": "user@example.com",
            "app_metadata": {},
            "user_metadata": {},
            "exp": int(now + exp_offset),
            "iat": int(now),
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _seed_profiles(db: Session) -> None:
    import uuid as _uuid

    for user in (USER_A, USER_B):
        # auth.users.id is a TEXT column (Supabase-owned stub).  PostgreSQL
        # stores UUIDs natively so there is no formatting distinction, but on
        # SQLite the PG_UUID bind-processor used by the ``profiles`` model
        # normalises to ``UUID.hex`` (no dashes).  Seed auth.users in the same
        # canonical form so the foreign-key to ``profiles.id`` resolves during
        # ORM-inserted profile creation.
        uid_hex = _uuid.UUID(user).hex
        db.execute(sa.text('INSERT INTO "auth.users" (id) VALUES (:id)'), {"id": uid_hex})
        db.execute(
            sa.text("INSERT INTO profiles (id, display_name) VALUES (:id, :name)"),
            {"id": uid_hex, "name": f"user-{user[:8]}"},
        )
    db.commit()


@pytest.fixture()
def api(db_session):
    """TestClient + two-user context, fully isolated per test."""
    _seed_profiles(db_session)

    settings = Settings()
    settings.supabase_url = ""  # legacy HS256 branch: deterministic
    settings.supabase_jwt_secret = TEST_SECRET
    settings.redis_url = ""
    settings.rate_limit_global_anon_per_minute = 1000
    settings.rate_limit_global_auth_per_minute = 1000
    settings.rate_limit_health_per_minute = 1000
    settings.rate_limit_favorites_per_minute = 1000
    settings.rate_limit_playlists_per_minute = 1000
    settings.rate_limit_playlist_tracks_per_minute = 1000
    settings.rate_limit_recently_played_per_minute = 1000
    settings.rate_limit_music_per_minute = 1000
    settings.rate_limit_auth_per_minute = 1000

    from app.api.deps import get_rate_limit_store
    from app.services.rate_limit import InMemoryRateLimitStore

    store = InMemoryRateLimitStore()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rate_limit_store] = lambda: store
    try:
        with TestClient(app) as c:
            yield Namespace(
                client=c,
                db=db_session,
                store=store,
                settings=settings,
                headers_a=_headers(USER_A),
                headers_b=_headers(USER_B),
                user_a=USER_A,
                user_b=USER_B,
            )
    finally:
        # Pop only what THIS fixture installed; clear() would also wipe the
        # autouse per-test rate-limit-store override from tests/conftest.py.
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_rate_limit_store, None)
