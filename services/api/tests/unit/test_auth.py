"""Unit and integration tests for the Supabase Auth foundation.

Coverage:
* :func:`app.services.auth.verify_supabase_token` — valid, expired,
  malformed, wrong-secret, wrong-audience, missing-secret, missing-sub.
* :func:`app.services.auth.get_authenticated_user_id` — valid UUID,
  missing ``sub``, non-UUID ``sub``.
* :func:`app.services.auth.ensure_profile_exists` — creates when absent,
  idempotent, multiple users, persists writable fields.
* ``GET /api/v1/auth/me`` — missing token, non-Bearer scheme, empty Bearer,
  valid token, expired token, malformed token, wrong-secret token,
  unconfigured JWT secret (500).
* JWT Signing Keys mode (:func:`verify_supabase_token_jwks`) — valid ES256
  token, invalid signature, expired, wrong issuer, wrong audience, HS256
  token rejected (algorithm confusion), unknown-kid rotation re-fetch,
  missing required claims, and the HTTP-level JWKS-mode path including the
  JWKS-preferred-over-secret precedence.
"""

from __future__ import annotations

import time as _time
from typing import Any
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient

from app.models import Profile
from app.services.auth import (
    AuthVerificationError,
    ensure_profile_exists,
    get_authenticated_user_id,
    verify_supabase_token,
    verify_supabase_token_jwks,
)


# ---------------------------------------------------------------------------
# Unit tests for verify_supabase_token
# ---------------------------------------------------------------------------


class TestVerifySupabaseToken:
    """Deterministic tests for JWT verification.

    These use a known secret and audience; no network calls are made.
    """

    @pytest.fixture
    def secret(self) -> str:
        return "test-jwt-secret"

    @pytest.fixture
    def audience(self) -> str:
        return "https://example.supabase.co"

    @pytest.fixture
    def user_id_hex(self) -> str:
        return "00000000-0000-0000-0000-000000000001"

    def _token(
        self,
        secret: str,
        audience: str,
        user_id_hex: str,
        exp_offset: int = 3600,
        now: float | None = None,
    ) -> str:
        now = now if now is not None else _time.time()
        return jwt.encode(
            {
                "sub": user_id_hex,
                "aud": audience,
                "role": "authenticated",
                "email": "user@example.com",
                "app_metadata": {},
                "user_metadata": {},
                "exp": int(now + exp_offset),
                "iat": int(now),
            },
            secret,
            algorithm="HS256",
        )

    def test_valid_token_returns_claims(
        self, secret, audience, user_id_hex
    ) -> None:
        token = self._token(secret, audience, user_id_hex)
        claims = verify_supabase_token(token, secret, audience)
        assert claims["sub"] == user_id_hex
        assert claims["aud"] == audience
        assert claims["role"] == "authenticated"

    def test_missing_secret_raises(self, audience) -> None:
        token = self._token("some-secret", audience, "some-id")
        with pytest.raises(
            AuthVerificationError, match="JWT secret is not configured"
        ):
            verify_supabase_token(token, "", audience)

    def test_wrong_signature_raises(self, audience, user_id_hex) -> None:
        token = self._token("correct-secret", audience, user_id_hex)
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token(token, "wrong-secret", audience)

    def test_expired_token_raises(self, secret, audience, user_id_hex) -> None:
        now = _time.time() - 7200
        token = self._token(secret, audience, user_id_hex, exp_offset=0, now=now)
        with pytest.raises(AuthVerificationError, match="expired"):
            verify_supabase_token(token, secret, audience)

    def test_wrong_audience_raises(self, secret, user_id_hex) -> None:
        token = self._token(secret, "https://example.supabase.co", user_id_hex)
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token(
                token, secret, "https://other-project.supabase.co"
            )

    def test_malformed_token_raises(self, secret, audience) -> None:
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token("not-a-jwt", secret, audience)

    def test_missing_sub_claim_raises(self, secret, audience) -> None:
        claims = {
            "aud": audience,
            "role": "authenticated",
            "email": "user@example.com",
            "app_metadata": {},
            "user_metadata": {},
            "exp": int(_time.time() + 3600),
        }
        token = jwt.encode(claims, secret, algorithm="HS256")
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token(token, secret, audience)
# ---------------------------------------------------------------------------
# Unit tests for get_authenticated_user_id
# ---------------------------------------------------------------------------


class TestGetAuthenticatedUserId:
    def test_extracts_uuid_from_sub(self) -> None:
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        claims = {"sub": str(user_id)}
        result = get_authenticated_user_id(claims)
        assert result == user_id

    def test_raises_on_missing_sub(self) -> None:
        with pytest.raises(AuthVerificationError, match="sub"):
            get_authenticated_user_id({})

    def test_raises_on_non_uuid_sub(self) -> None:
        with pytest.raises(AuthVerificationError, match="UUID"):
            get_authenticated_user_id({"sub": "not-a-uuid"})


# ---------------------------------------------------------------------------
# Unit tests for ensure_profile_exists
# ---------------------------------------------------------------------------


class TestEnsureProfileExists:
    """Tests for the idempotent profile synchronization function.

    These require a database session.  The suite's shared fixture forces
    ``DATABASE_URL`` to an in-memory SQLite database so these tests are
    hermetic.
    """

    @staticmethod
    def _seed_auth_user(db_session, user_id: UUID) -> None:
        """Insert the auth.users stub row so the FK to profiles.id resolves.

        On SQLite PG_UUID's bind-processor normalises to ``UUID.hex`` (no
        dashes); PostgreSQL stores UUIDs natively so there is no formatting
        distinction in production.
        """
        import sqlalchemy as sa

        db_session.execute(
            sa.text('INSERT INTO "auth.users" (id) VALUES (:id)'),
            {"id": user_id.hex},
        )
        db_session.commit()

    def test_creates_profile_when_absent(self, db_session) -> None:
        user_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self._seed_auth_user(db_session, user_id)
        profile = ensure_profile_exists(db_session, user_id)
        assert profile.id == str(user_id)
        assert profile.display_name is None
        assert profile.avatar_url is None

    def test_is_idempotent(self, db_session) -> None:
        user_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self._seed_auth_user(db_session, user_id)
        first = ensure_profile_exists(db_session, user_id)
        second = ensure_profile_exists(db_session, user_id)
        assert second is first
        assert str(second.id) == str(user_id)

    def test_different_users_get_different_rows(self, db_session) -> None:
        user_a = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        user_b = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        self._seed_auth_user(db_session, user_a)
        self._seed_auth_user(db_session, user_b)
        profile_a = ensure_profile_exists(db_session, user_a)
        profile_b = ensure_profile_exists(db_session, user_b)
        assert profile_a.id != profile_b.id
        assert profile_a.id == str(user_a)
        assert profile_b.id == str(user_b)

    def test_populated_profile_persists_display_name(self, db_session) -> None:
        user_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self._seed_auth_user(db_session, user_id)
        profile = ensure_profile_exists(db_session, user_id)
        profile.display_name = "Test User"
        profile.avatar_url = "https://example.com/avatar.png"
        db_session.commit()

        reloaded = ensure_profile_exists(db_session, user_id)
        assert reloaded.display_name == "Test User"
        assert reloaded.avatar_url == "https://example.com/avatar.png"


# ---------------------------------------------------------------------------
# HTTP integration tests for /api/v1/auth/me
# ---------------------------------------------------------------------------


class TestAuthMeEndpoint:
    """Tests for ``GET /api/v1/auth/me``.

    Uses the shared ``client`` fixture and header fixtures from conftest.
    """

    def test_requires_bearer_token(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        detail = response.json()["detail"].lower()
        assert "bearer" in detail or "authorization" in detail

    def test_rejects_non_bearer_scheme(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code == 401

    def test_rejects_empty_bearer_token(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_accepts_valid_token(
        self, client: TestClient, auth_token_headers: dict[str, str]
    ) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        settings = Settings()
        settings.supabase_jwt_secret = "test-jwt-secret-do-not-expose"
        settings.supabase_url = ""  # legacy HS256 branch: no SUPABASE_URL
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get("/api/v1/auth/me", headers=auth_token_headers)
            assert response.status_code == 200
            body = response.json()
            assert "id" in body
            assert body["id"] == "00000000-0000-0000-0000-000000000001"
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_rejects_expired_token(
        self, client: TestClient, expired_auth_token_headers: dict[str, str]
    ) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        settings = Settings()
        settings.supabase_jwt_secret = "test-jwt-secret-do-not-expose"
        settings.supabase_url = ""  # legacy HS256 branch: no SUPABASE_URL
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get(
                "/api/v1/auth/me", headers=expired_auth_token_headers
            )
            assert response.status_code == 401
            assert "expired" in response.json()["detail"]
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_rejects_malformed_token(
        self, client: TestClient, jwt_secret: str, jwt_audience: str
    ) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        settings = Settings()
        settings.supabase_jwt_secret = jwt_secret
        settings.supabase_url = ""  # legacy HS256 branch: no SUPABASE_URL
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            headers = {"Authorization": "Bearer not-a-jwt"}
            response = client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_rejects_wrong_secret_token(
        self, client: TestClient, jwt_audience: str, user_id_hex: str
    ) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        settings = Settings()
        settings.supabase_jwt_secret = "correct-secret-for-test"
        settings.supabase_url = ""  # legacy HS256 branch: no SUPABASE_URL
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            token = jwt.encode(
                {
                    "sub": user_id_hex,
                    "aud": jwt_audience,
                    "role": "authenticated",
                    "email": "user@example.com",
                    "app_metadata": {},
                    "user_metadata": {},
                    "exp": int(_time.time() + 3600),
                    "iat": int(_time.time()),
                },
                "wrong-secret",
                algorithm="HS256",
            )
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_returns_500_when_jwt_secret_unconfigured(
        self, client: TestClient, user_id_hex: str
    ) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        original = get_settings()
        settings = Settings()
        settings.supabase_jwt_secret = ""
        settings.supabase_url = ""  # neither JWKS nor legacy configured -> 500
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            token = jwt.encode(
                {
                    "sub": user_id_hex,
                    "aud": "https://example.supabase.co",
                    "role": "authenticated",
                    "email": "user@example.com",
                    "app_metadata": {},
                    "user_metadata": {},
                    "exp": int(_time.time() + 3600),
                    "iat": int(_time.time()),
                },
                "any-secret-will-fail-because-verification-is-not-attempted",
                algorithm="HS256",
            )
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 500
            body = response.json()
            assert body["detail"] == "Authentication service unavailable"
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)


# ---------------------------------------------------------------------------
# Profile sync integration documentation
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_sync_demo(db_session):
    """A minimal demonstration of how ``ensure_profile_exists`` is intended
    to be called from real endpoints.

    This is intentionally lightweight — it exists to document the intended
    call pattern without coupling this file to endpoint-specific logic.
    """
    import sqlalchemy as sa

    user_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    # Seed the auth.users stub so the FK to profiles.id resolves under SQLite.
    # On SQLite PG_UUID's bind-processor normalises to ``UUID.hex`` (no dashes);
    # PostgreSQL stores UUIDs natively so there is no formatting distinction in
    # production.
    db_session.execute(
        sa.text('INSERT INTO "auth.users" (id) VALUES (:id)'),
        {"id": user_id.hex},
    )
    db_session.commit()
    return ensure_profile_exists(db_session, user_id)


def test_profile_sync_demo(profile_sync_demo: Profile) -> None:
    """Sanity check that the demo fixture creates a profile row."""
    assert profile_sync_demo.id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert profile_sync_demo.display_name is None


# ---------------------------------------------------------------------------
# JWT Signing Keys mode (ES256 via JWKS)
# ---------------------------------------------------------------------------


class _FakePyJWK:
    """Minimal stand-in for ``jwt.PyJWK`` wrapping a local EC public key."""

    def __init__(self, key) -> None:  # noqa: ANN001
        self.key = key


class _FakePyJWKClient:
    """A ``PyJWKClient`` substitute backed by locally generated EC keys.

    ``get_signing_key_from_jwt`` resolves the token's ``kid`` against the
    configured key map, exactly like the real client resolves it against the
    project JWKS — but without any network access.  ``fetches`` counts JWKS
    lookups so key-rotation behavior can be asserted.
    """

    def __init__(self, keys: dict) -> None:
        self._keys = dict(keys)
        self.fetches = 0

    def get_signing_key_from_jwt(self, token: str):  # noqa: ANN201
        header = jwt.get_unverified_header(token)
        self.fetches += 1
        kid = header.get("kid")
        if kid not in self._keys:
            raise jwt.PyJWKClientError(
                f"Unable to find a signing key that matches: {kid!r}"
            )
        return _FakePyJWK(self._keys[kid])


class TestVerifySupabaseTokenJwks:
    """Deterministic, network-free tests for the asymmetric signing-keys mode."""

    audience = "https://example.supabase.co"
    issuer = "https://example.supabase.co/auth/v1"
    user_id_hex = "00000000-0000-0000-0000-000000000002"

    @staticmethod
    def _make_keypair(kid: str):
        """Generate a P-256 keypair; return (private_key, public_key)."""
        from cryptography.hazmat.primitives.asymmetric import ec

        private_key = ec.generate_private_key(ec.SECP256R1())
        return private_key, private_key.public_key()

    def _token(
        self,
        private_key,
        kid: str,
        audience=None,  # noqa: ANN001
        issuer=None,  # noqa: ANN001
        exp_offset: int = 3600,
        algorithm: str = "ES256",
    ) -> str:
        now = _time.time()
        claims: dict[str, Any] = {
            "sub": self.user_id_hex,
            "aud": audience if audience is not None else self.audience,
            "role": "authenticated",
            "iss": issuer if issuer is not None else self.issuer,
            "exp": int(now + exp_offset),
            "iat": int(now),
            "email": "user@example.com",
            "app_metadata": {},
            "user_metadata": {},
        }
        return jwt.encode(claims, private_key, algorithm=algorithm, headers={"kid": kid})

    def test_valid_es256_token_returns_claims(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        claims = verify_supabase_token_jwks(
            self._token(priv, "kid-1"), client, self.audience
        )
        assert claims["sub"] == self.user_id_hex
        assert claims["role"] == "authenticated"
        assert claims["iss"] == self.issuer

    def test_invalid_signature_rejected(self) -> None:
        priv_a, pub_a = self._make_keypair("kid-a")
        priv_b, _ = self._make_keypair("kid-b")
        # JWKS publishes kid-a, but the token was signed by a different key.
        client = _FakePyJWKClient({"kid-a": pub_a})
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(self._token(priv_b, "kid-a"), client, self.audience)

    def test_expired_token_rejected(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        token = self._token(priv, "kid-1", exp_offset=-3600)
        with pytest.raises(AuthVerificationError, match="expired"):
            verify_supabase_token_jwks(token, client, self.audience)

    def test_wrong_issuer_rejected(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        token = self._token(priv, "kid-1", issuer="https://evil.example.com/auth/v1")
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(token, client, self.audience)

    def test_wrong_audience_rejected(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        token = self._token(priv, "kid-1", audience="https://other.supabase.co")
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(token, client, self.audience)

    def test_hs256_token_rejected_algorithm_confusion(self) -> None:
        """A symmetric token must never be accepted in the asymmetric mode."""
        hs256_token = jwt.encode(
            {
                "sub": self.user_id_hex,
                "aud": self.audience,
                "role": "authenticated",
                "iss": self.issuer,
                "exp": int(_time.time() + 3600),
            },
            "attacker-controlled-secret",
            algorithm="HS256",
            headers={"kid": "kid-1"},
        )
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(hs256_token, client, self.audience)

    def test_unknown_kid_rejected(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        token = self._token(priv, "kid-rotated-away")
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(token, client, self.audience)

    def test_key_rotation_new_kid_is_resolved(self) -> None:
        """After rotation the client resolves the new kid from the JWKS."""
        priv_old, pub_old = self._make_keypair("kid-old")
        priv_new, pub_new = self._make_keypair("kid-new")
        client = _FakePyJWKClient({"kid-old": pub_old})

        token_old = self._token(priv_old, "kid-old")
        assert verify_supabase_token_jwks(token_old, client, self.audience)["sub"] == self.user_id_hex

        # Rotation: the JWKS now also contains the new key.  The same client
        # instance picks up the new kid.
        client._keys["kid-new"] = pub_new
        token_new = self._token(priv_new, "kid-new")
        claims = verify_supabase_token_jwks(token_new, client, self.audience)
        assert claims["sub"] == self.user_id_hex

        # The old key remains valid until removed from the JWKS...
        assert verify_supabase_token_jwks(token_old, client, self.audience)["sub"] == self.user_id_hex
        # ...and stops verifying once it is revoked/removed.
        del client._keys["kid-old"]
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(token_old, client, self.audience)

    def test_refreshed_access_token_accepted_after_expiry(self) -> None:
        """A token re-issued after expiry (Supabase session refresh) verifies.

        Models the mobile flow: the access token expires, the Supabase client
        transparently refreshes it, and the API accepts the NEW token while
        continuing to reject the old expired one.
        """
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})

        expired_token = self._token(priv, "kid-1", exp_offset=-60)
        with pytest.raises(AuthVerificationError, match="expired"):
            verify_supabase_token_jwks(expired_token, client, self.audience)

        refreshed_token = self._token(priv, "kid-1", exp_offset=3600)
        claims = verify_supabase_token_jwks(refreshed_token, client, self.audience)
        assert claims["sub"] == self.user_id_hex

    def test_missing_required_claim_rejected(self) -> None:
        priv, pub = self._make_keypair("kid-1")
        client = _FakePyJWKClient({"kid-1": pub})
        token_no_iss = jwt.encode(
            {
                "sub": self.user_id_hex,
                "aud": self.audience,
                "role": "authenticated",
                "exp": int(_time.time() + 3600),
            },
            priv,
            algorithm="ES256",
            headers={"kid": "kid-1"},
        )
        with pytest.raises(AuthVerificationError, match="Invalid token"):
            verify_supabase_token_jwks(token_no_iss, client, self.audience)

    def test_none_jwks_client_rejected(self) -> None:
        with pytest.raises(AuthVerificationError, match="JWKS client is not configured"):
            verify_supabase_token_jwks("anything", None, self.audience)


class TestCreateJwksClient:
    def test_rejects_empty_url(self) -> None:
        from app.services.auth import create_jwks_client

        with pytest.raises(AuthVerificationError, match="SUPABASE_URL is not configured"):
            create_jwks_client("")

    def test_builds_cached_client_with_correct_uri(self) -> None:
        from app.services.auth import create_jwks_client

        client = create_jwks_client("https://example.supabase.co/")
        assert client.uri == "https://example.supabase.co/auth/v1/.well-known/jwks.json"
        # PyJWT caches the fetched JWK set by default; caching must be on so
        # the endpoint is not hit on every request.
        assert client.jwk_set_cache is not None


class TestHttpJwksMode:
    """``GET /api/v1/auth/me`` behavior when SUPABASE_URL is configured."""

    audience = "https://example.supabase.co"
    issuer = "https://example.supabase.co/auth/v1"
    user_id_hex = "00000000-0000-0000-0000-000000000003"

    def _es_token(self, private_key, kid: str, exp_offset: int = 3600) -> str:
        now = _time.time()
        return jwt.encode(
            {
                "sub": self.user_id_hex,
                "aud": self.audience,
                "role": "authenticated",
                "iss": self.issuer,
                "exp": int(now + exp_offset),
                "iat": int(now),
                "email": "user@example.com",
                "app_metadata": {},
                "user_metadata": {},
            },
            private_key,
            algorithm="ES256",
            headers={"kid": kid},
        )

    @staticmethod
    def _keypair():
        from cryptography.hazmat.primitives.asymmetric import ec

        priv = ec.generate_private_key(ec.SECP256R1())
        return priv, priv.public_key()

    def test_jwks_mode_preferred_over_legacy_secret(
        self, client: TestClient
    ) -> None:
        import app.api.routes.auth as auth_routes
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        priv, pub = self._keypair()
        fake_client = _FakePyJWKClient({"kid-http": pub})
        token = self._es_token(priv, "kid-http")

        settings = Settings()
        settings.supabase_url = self.audience
        settings.supabase_jwt_secret = "legacy-secret-must-not-be-used"

        saved_factory = auth_routes._jwks_client_for
        auth_routes._jwks_client_for = lambda url: fake_client  # type: ignore[assignment]
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            assert response.json()["id"] == self.user_id_hex
            assert fake_client.fetches >= 1, "JWKS mode must have been used"
        finally:
            auth_routes._jwks_client_for = saved_factory  # type: ignore[assignment]
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_jwks_mode_invalid_signature_401(self, client: TestClient) -> None:
        from cryptography.hazmat.primitives.asymmetric import ec

        import app.api.routes.auth as auth_routes
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        _, pub_published = self._keypair()
        priv_wrong = ec.generate_private_key(ec.SECP256R1())
        fake_client = _FakePyJWKClient({"kid-http": pub_published})
        token = self._es_token(priv_wrong, "kid-http")

        settings = Settings()
        settings.supabase_url = self.audience

        saved_factory = auth_routes._jwks_client_for
        auth_routes._jwks_client_for = lambda url: fake_client  # type: ignore[assignment]
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401
        finally:
            auth_routes._jwks_client_for = saved_factory  # type: ignore[assignment]
            fastapi_app.dependency_overrides.pop(get_settings, None)

    def test_500_when_no_auth_configuration(self, client: TestClient) -> None:
        from app.config import Settings, get_settings
        from app.main import app as fastapi_app

        settings = Settings()
        settings.supabase_url = ""
        settings.supabase_jwt_secret = ""
        fastapi_app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer not-even-a-jwt"},
            )
            assert response.status_code == 500
            assert response.json()["detail"] == "Authentication service unavailable"
        finally:
            fastapi_app.dependency_overrides.pop(get_settings, None)

