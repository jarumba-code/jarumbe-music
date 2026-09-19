"""Rate-limiting tests for the Jarumba API.

Covers the documented policy (docs/security.md):

* fixed-window counters (60s default window),
* authenticated identity = verified JWT user; anonymous identity = client IP,
* invalid / expired / wrong-signature tokens are charged to the anonymous
  (IP) bucket - they can never bypass the limiter because rate limiting is a
  route-level dependency resolved before JWT verification,
* global and endpoint-specific buckets are separate and interact predictably
  (every applicable bucket is incremented; the first exceeded one wins),
* structured 429 responses with ``Retry-After`` and ``X-RateLimit-*`` headers,
* explicit trusted-proxy policy for ``X-Forwarded-For``,
* Redis backend: atomic increment+expiry, explicit timeouts, fail-open for
  normal endpoints and fail-closed (503) for auth endpoints when Redis is
  unavailable, and the production requirement for ``REDIS_URL``.

No real Redis instance is contacted: the "unavailable Redis" tests point at a
guaranteed-closed local port (127.0.0.1:1), and the atomic-script test uses a
recording fake client.
"""

from __future__ import annotations

import time as _time
from types import SimpleNamespace as Namespace

import jwt as pyjwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import app.services.rate_limit as rate_limit_module
from app.config import Settings, get_settings
from app.database import get_db
from app.main import app
from app.services.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitRule,
    RedisRateLimitStore,
    build_rate_limit_store,
    client_ip,
    enforce_rate_limit,
    require_shared_rate_limit_backend,
)

from tests.unit.api_testbed import (
    TEST_SECRET,
    USER_A,
    USER_B,
    _headers,
    _seed_profiles,
)

# A guaranteed-closed local port: connection attempts fail immediately with
# connection-refused on every supported platform.  Never a real Redis.
_DEAD_REDIS_URL = "redis://127.0.0.1:1/0"


# ---------------------------------------------------------------------------
# Fixture: TestClient with configurable limits and a fresh in-process store
# ---------------------------------------------------------------------------


@pytest.fixture()
def rl(db_session):
    """TestClient + two-user context with per-test adjustable rate limits."""
    _seed_profiles(db_session)

    settings = Settings()
    settings.supabase_url = ""  # legacy HS256 branch: deterministic, no network
    settings.supabase_jwt_secret = TEST_SECRET
    settings.redis_url = ""
    # Generous defaults; individual tests tighten the bucket under test.
    for name in (
        "global_anon",
        "global_auth",
        "auth",
        "health",
        "music",
        "favorites",
        "playlists",
        "playlist_tracks",
        "recently_played",
        "profile",
    ):
        setattr(settings, f"rate_limit_{name}_per_minute", 1000)

    store = InMemoryRateLimitStore()

    def _override_get_db():
        yield db_session

    from app.api.deps import get_rate_limit_store

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rate_limit_store] = lambda: store
    try:
        with TestClient(app) as client:
            yield Namespace(
                client=client,
                db=db_session,
                settings=settings,
                store=store,
                headers_a=_headers(USER_A),
                headers_b=_headers(USER_B),
            )
    finally:
        # Pop only what this fixture installed (never clear(): the autouse
        # per-test limiter override from tests/conftest.py must survive).
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_rate_limit_store, None)


# ---------------------------------------------------------------------------
# 429 response shape
# ---------------------------------------------------------------------------


class TestRateLimitResponse:
    def test_429_is_structured_json(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 2
        rl.settings.rate_limit_health_per_minute = 1000
        for _ in range(2):
            assert rl.client.get("/health").status_code == 200

        response = rl.client.get("/health")
        assert response.status_code == 429
        body = response.json()
        assert body["detail"] == "Rate limit exceeded"
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "2"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Scope"] == "global"

    def test_retry_after_is_within_the_window(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 1
        rl.settings.rate_limit_health_per_minute = 1000
        assert rl.client.get("/health").status_code == 200

        response = rl.client.get("/health")
        assert response.status_code == 429
        retry_after = int(response.headers["Retry-After"])
        window = rl.settings.rate_limit_window_seconds
        assert 1 <= retry_after <= window + 1

    def test_429_body_contains_no_internals(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 1
        rl.settings.rate_limit_health_per_minute = 1000
        rl.client.get("/health")
        response = rl.client.get("/health")
        text = response.text
        for secret_marker in ("redis://", "postgres", "SECRET", "sqlite"):
            assert secret_marker not in text


# ---------------------------------------------------------------------------
# Identity separation
# ---------------------------------------------------------------------------


class TestIdentityBuckets:
    def test_different_authenticated_users_have_separate_buckets(self, rl):
        rl.settings.rate_limit_global_auth_per_minute = 2
        rl.settings.rate_limit_profile_per_minute = 1000
        for _ in range(2):
            assert (
                rl.client.get("/api/v1/profile", headers=rl.headers_a).status_code
                == 200
            )
        assert (
            rl.client.get("/api/v1/profile", headers=rl.headers_a).status_code == 429
        )
        # User B has a completely separate bucket.
        assert (
            rl.client.get("/api/v1/profile", headers=rl.headers_b).status_code == 200
        )

    def test_unauthenticated_requests_share_one_ip_bucket(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 3
        rl.settings.rate_limit_health_per_minute = 1000
        for _ in range(3):
            assert rl.client.get("/health").status_code == 200
        assert rl.client.get("/health").status_code == 429

    def test_authenticated_and_anonymous_buckets_are_separate(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 1
        rl.settings.rate_limit_global_auth_per_minute = 10
        rl.settings.rate_limit_health_per_minute = 1000
        # Exhaust the anonymous bucket...
        assert rl.client.get("/health").status_code == 200
        assert rl.client.get("/health").status_code == 429
        # ...the authenticated bucket is unaffected.
        assert rl.client.get("/health", headers=rl.headers_a).status_code == 200


# ---------------------------------------------------------------------------
# Invalid tokens cannot bypass the limiter
# ---------------------------------------------------------------------------


class TestInvalidTokensAreLimited:
    def test_malformed_token_charged_to_anon_bucket(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 3
        rl.settings.rate_limit_profile_per_minute = 1000
        bad = {"Authorization": "Bearer not-a-jwt"}
        # 401s while the bucket lasts...
        assert rl.client.get("/api/v1/profile", headers=bad).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=bad).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=bad).status_code == 401
        # ...then the limiter wins over the authenticator.
        response = rl.client.get("/api/v1/profile", headers=bad)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "global"

    def test_expired_token_charged_to_anon_bucket(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 2
        rl.settings.rate_limit_profile_per_minute = 1000
        now = _time.time() - 7200
        expired = pyjwt.encode(
            {
                "sub": USER_A,
                "aud": "https://example.supabase.co",
                "role": "authenticated",
                "email": "user@example.com",
                "app_metadata": {},
                "user_metadata": {},
                "exp": int(now),
                "iat": int(now),
            },
            TEST_SECRET,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {expired}"}
        assert rl.client.get("/api/v1/profile", headers=headers).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=headers).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=headers).status_code == 429

    def test_wrong_signature_token_charged_to_anon_bucket(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 1
        rl.settings.rate_limit_profile_per_minute = 1000
        token = pyjwt.encode(
            {
                "sub": USER_A,
                "aud": "https://example.supabase.co",
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
        assert rl.client.get("/api/v1/profile", headers=headers).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=headers).status_code == 429

    def test_invalid_tokens_do_not_consume_a_valid_users_bucket(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 1
        rl.settings.rate_limit_global_auth_per_minute = 10
        rl.settings.rate_limit_profile_per_minute = 1000
        bad = {"Authorization": "Bearer not-a-jwt"}
        assert rl.client.get("/api/v1/profile", headers=bad).status_code == 401
        assert rl.client.get("/api/v1/profile", headers=bad).status_code == 429
        # The valid user's authenticated bucket is untouched by anon traffic.
        assert (
            rl.client.get("/api/v1/profile", headers=rl.headers_a).status_code == 200
        )



# ---------------------------------------------------------------------------
# Endpoint-specific vs global buckets
# ---------------------------------------------------------------------------


class TestBucketInteraction:
    def test_favorites_endpoint_limit(self, rl):
        rl.settings.rate_limit_favorites_per_minute = 2
        rl.settings.rate_limit_global_auth_per_minute = 1000
        for _ in range(2):
            assert (
                rl.client.get("/api/v1/favorites", headers=rl.headers_a).status_code
                == 200
            )
        response = rl.client.get("/api/v1/favorites", headers=rl.headers_a)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "favorites"
        assert response.headers["X-RateLimit-Limit"] == "2"

    def test_endpoint_buckets_are_scoped_separately(self, rl):
        rl.settings.rate_limit_favorites_per_minute = 2
        rl.settings.rate_limit_playlists_per_minute = 1000
        rl.settings.rate_limit_global_auth_per_minute = 1000
        rl.client.get("/api/v1/favorites", headers=rl.headers_a)
        rl.client.get("/api/v1/favorites", headers=rl.headers_a)
        assert (
            rl.client.get("/api/v1/favorites", headers=rl.headers_a).status_code == 429
        )
        # A different endpoint bucket is untouched.
        assert (
            rl.client.get("/api/v1/playlists", headers=rl.headers_a).status_code == 200
        )

    def test_global_bucket_spans_endpoints(self, rl):
        rl.settings.rate_limit_global_auth_per_minute = 3
        rl.settings.rate_limit_favorites_per_minute = 1000
        rl.settings.rate_limit_playlists_per_minute = 1000
        assert (
            rl.client.get("/api/v1/favorites", headers=rl.headers_a).status_code == 200
        )
        assert (
            rl.client.get("/api/v1/favorites", headers=rl.headers_a).status_code == 200
        )
        assert (
            rl.client.get("/api/v1/playlists", headers=rl.headers_a).status_code == 200
        )
        response = rl.client.get("/api/v1/playlists", headers=rl.headers_a)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "global"


    def test_profile_limiting(self, rl):
        rl.settings.rate_limit_profile_per_minute = 2
        rl.settings.rate_limit_global_auth_per_minute = 1000
        assert (
            rl.client.get("/api/v1/profile", headers=rl.headers_a).status_code == 200
        )
        assert (
            rl.client.get("/api/v1/profile", headers=rl.headers_a).status_code == 200
        )
        response = rl.client.get("/api/v1/profile", headers=rl.headers_a)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "profile"

    def test_health_limiting(self, rl):
        rl.settings.rate_limit_health_per_minute = 1
        rl.settings.rate_limit_global_anon_per_minute = 1000
        assert rl.client.get("/health").status_code == 200
        response = rl.client.get("/health")
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "health"

    def test_auth_scope_limiting(self, rl):
        rl.settings.rate_limit_auth_per_minute = 1
        rl.settings.rate_limit_global_auth_per_minute = 1000
        assert (
            rl.client.get("/api/v1/auth/me", headers=rl.headers_a).status_code == 200
        )
        response = rl.client.get("/api/v1/auth/me", headers=rl.headers_a)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Scope"] == "auth"


# ---------------------------------------------------------------------------
# Forwarded-IP / trusted-proxy policy
# ---------------------------------------------------------------------------


class TestTrustedProxyPolicy:
    def test_spoofed_forwarded_for_ignored_by_default(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 2
        rl.settings.rate_limit_health_per_minute = 1000
        # trust_proxy_headers defaults to False: every spoofed identity maps
        # onto the same peer bucket.
        assert (
            rl.client.get(
                "/health", headers={"X-Forwarded-For": "203.0.113.9"}
            ).status_code
            == 200
        )
        assert (
            rl.client.get(
                "/health", headers={"X-Forwarded-For": "203.0.113.9"}
            ).status_code
            == 200
        )
        # A "fresh" spoofed identity changes nothing: the peer bucket is used.
        assert (
            rl.client.get(
                "/health", headers={"X-Forwarded-For": "203.0.113.77"}
            ).status_code
            == 429
        )

    def test_forwarded_for_honored_for_trusted_proxy(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 2
        rl.settings.rate_limit_health_per_minute = 1000
        rl.settings.trust_proxy_headers = True
        rl.settings.trusted_proxy_ips = "testclient"
        rl.settings.trusted_proxy_count = 1

        # Two requests from "client" 198.51.100.7 fill that bucket...
        for _ in range(2):
            response = rl.client.get(
                "/health", headers={"X-Forwarded-For": "198.51.100.7"}
            )
            assert response.status_code == 200
        response = rl.client.get(
            "/health", headers={"X-Forwarded-For": "198.51.100.7"}
        )
        assert response.status_code == 429
        # ...a different client IP still has its own fresh bucket.
        response = rl.client.get(
            "/health", headers={"X-Forwarded-For": "198.51.100.8"}
        )
        assert response.status_code == 200


    def test_untrusted_peer_ignores_forwarded_for_even_when_enabled(self, rl):
        rl.settings.rate_limit_global_anon_per_minute = 2
        rl.settings.rate_limit_health_per_minute = 1000
        rl.settings.trust_proxy_headers = True
        rl.settings.trusted_proxy_ips = "10.0.0.7"  # the ASGI peer is not this
        for _ in range(2):
            response = rl.client.get(
                "/health", headers={"X-Forwarded-For": "198.51.100.7"}
            )
            assert response.status_code == 200
        assert rl.client.get("/health").status_code == 429

    def test_multi_hop_forwarded_for_skips_trusted_hops(self):
        settings = Settings()
        settings.trust_proxy_headers = True
        settings.trusted_proxy_ips = "testclient"
        # Convention: trusted_proxy_count is the number of trusted proxies in
        # front of the API; each proxy appends the peer it received from.
        # Path: client -> proxy1 -> peer(proxy2): XFF = "client, proxy1",
        # so with two trusted proxies the client is hops[len - 2].
        settings.trusted_proxy_count = 2
        request = Request(
            {
                "type": "http",
                "client": ("testclient", 50000),
                "headers": [
                    (b"x-forwarded-for", b"198.51.100.1, 10.0.0.7"),
                ],
            }
        )
        assert client_ip(request, settings) == "198.51.100.1"
        # A single trusted proxy (the direct peer): the last XFF entry is the
        # client as observed by that proxy.
        settings.trusted_proxy_count = 1
        assert client_ip(request, settings) == "10.0.0.7"

    def test_overlong_forwarded_for_falls_back_to_peer(self):
        settings = Settings()
        settings.trust_proxy_headers = True
        settings.trusted_proxy_ips = "testclient"
        request = Request(
            {
                "type": "http",
                "client": ("testclient", 50000),
                "headers": [(b"x-forwarded-for", b"198.51.100.7 " * 200)],
            }
        )
        assert client_ip(request, settings) == "testclient"

    def test_non_ip_forwarded_for_value_falls_back_to_peer(self):
        settings = Settings()
        settings.trust_proxy_headers = True
        settings.trusted_proxy_ips = "testclient"
        request = Request(
            {
                "type": "http",
                "client": ("testclient", 50000),
                "headers": [(b"x-forwarded-for", b"not-an-ip")],
            }
        )
        assert client_ip(request, settings) == "testclient"



# ---------------------------------------------------------------------------
# Store behaviour (in-process + Redis contract)
# ---------------------------------------------------------------------------


class TestInMemoryStore:
    async def test_counts_and_reports_reset(self):
        store = InMemoryRateLimitStore()
        count, reset_in = await store.increment("global:anon:1.2.3.4", 60)
        assert count == 1
        assert 1 <= reset_in <= 61
        count, _ = await store.increment("global:anon:1.2.3.4", 60)
        assert count == 2

    async def test_window_expiry_resets_the_counter(self):
        store = InMemoryRateLimitStore()
        await store.increment("k", 60)
        await store.increment("k", 60)
        count, _ = await store.increment("k", 60)
        assert count == 3
        # Simulate the window rolling over.
        key_count, window_start = store._counters["k"]
        store._counters["k"] = (key_count, window_start - 61)
        count, _ = await store.increment("k", 60)
        assert count == 1


class _RecordingFakeRedis:
    """Async stand-in capturing every ``eval`` invocation."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def eval(self, script, numkeys, *keys_and_args):  # noqa: ANN001
        self.calls.append((script, numkeys, keys_and_args))
        return 1


class TestRedisStore:
    def test_increment_and_expiry_are_one_atomic_script(self):
        script = RedisRateLimitStore.INCREMENT_SCRIPT
        # INCR and EXPIRE live in a single Lua script: increment and TTL can
        # never be separated by a crash or a second replica.
        assert "INCR" in script
        assert "EXPIRE" in script
        assert "if current == 1" in script  # TTL applied on first write only

    async def test_increment_issues_exactly_one_eval(self):
        fake = _RecordingFakeRedis()
        store = RedisRateLimitStore(_DEAD_REDIS_URL, client=fake)
        count, reset_in = await store.increment("global:anon:1.2.3.4", 60)
        assert count == 1
        assert len(fake.calls) == 1
        _, numkeys, args = fake.calls[0]
        assert numkeys == 1
        assert args[0].startswith("ratelimit:global:anon:")
        assert args[1] == "61"  # TTL = window + 1

    def test_explicit_connect_and_command_timeouts(self, monkeypatch):
        captured: dict = {}

        def fake_from_url(url, **kwargs):  # noqa: ANN001, ANN202
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(rate_limit_module.aioredis, "from_url", fake_from_url)
        RedisRateLimitStore(
            "redis://localhost:6379/0",
            connect_timeout=2.5,
            command_timeout=3.5,
        )
        assert captured["socket_connect_timeout"] == 2.5
        assert captured["socket_timeout"] == 3.5
        assert captured["decode_responses"] is True

    async def test_unreachable_redis_raises_quickly(self):
        store = RedisRateLimitStore(
            _DEAD_REDIS_URL, connect_timeout=0.5, command_timeout=0.5
        )
        started = _time.monotonic()
        with pytest.raises(Exception):  # noqa: B017, PT011
            await store.increment("k", 60)
        elapsed = _time.monotonic() - started
        assert elapsed < 5.0, "an unresponsive Redis must fail fast"



# ---------------------------------------------------------------------------
# Failure policy: fail-open vs fail-closed
# ---------------------------------------------------------------------------


@pytest.fixture()
def dead_redis_app(db_session):
    """App wired to a Redis store whose backend is guaranteed unreachable."""
    _seed_profiles(db_session)
    settings = Settings()
    settings.supabase_url = ""
    settings.supabase_jwt_secret = TEST_SECRET
    settings.redis_url = _DEAD_REDIS_URL  # non-empty -> production-style config
    settings.rate_limit_allow_memory_fallback = False
    for name in ("global_anon", "global_auth", "health", "profile", "auth"):
        setattr(settings, f"rate_limit_{name}_per_minute", 1000)

    store = RedisRateLimitStore(
        _DEAD_REDIS_URL, connect_timeout=0.5, command_timeout=0.5
    )

    def _override_get_db():
        yield db_session

    from app.api.deps import get_rate_limit_store

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rate_limit_store] = lambda: store
    try:
        with TestClient(app) as client:
            yield Namespace(client=client, headers_a=_headers(USER_A))
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_rate_limit_store, None)


class TestRedisUnavailablePolicy:
    def test_fail_open_for_normal_endpoints(self, dead_redis_app):
        # /health uses the default (fail-open) policy: a Redis outage must not
        # take the API down.
        assert dead_redis_app.client.get("/health").status_code == 200

    def test_fail_closed_for_auth_endpoint(self, dead_redis_app):
        # /api/v1/auth/me is auth-sensitive: a Redis outage must NOT open the
        # door to unlimited token probing, so the limiter fails closed.
        response = dead_redis_app.client.get(
            "/api/v1/auth/me", headers=dead_redis_app.headers_a
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()



# ---------------------------------------------------------------------------
# Environment policy: production requires a shared backend
# ---------------------------------------------------------------------------


class TestProductionRedisRequirement:
    def _settings(self, **overrides) -> Settings:
        settings = Settings()
        settings.redis_url = ""
        settings.rate_limit_allow_memory_fallback = False
        settings.environment = "production"
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_production_without_redis_fails_fast(self):
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            require_shared_rate_limit_backend(self._settings())

    def test_production_with_redis_is_accepted(self):
        require_shared_rate_limit_backend(
            self._settings(redis_url="redis://localhost:6379/0")
        )

    def test_production_with_explicit_memory_fallback_optin_is_accepted(self):
        require_shared_rate_limit_backend(
            self._settings(rate_limit_allow_memory_fallback=True)
        )

    def test_development_keeps_the_local_fallback(self):
        settings = self._settings()
        settings.environment = "development"
        require_shared_rate_limit_backend(settings)

    def test_build_store_prefers_redis_when_configured(self):
        settings = self._settings(redis_url="redis://localhost:6379/0")
        assert isinstance(build_rate_limit_store(settings), RedisRateLimitStore)

    def test_build_store_uses_memory_when_no_redis_and_local_env(self):
        settings = self._settings()
        settings.environment = "development"
        assert isinstance(build_rate_limit_store(settings), InMemoryRateLimitStore)



# ---------------------------------------------------------------------------
# Enforcement primitive
# ---------------------------------------------------------------------------


class FakeRequest:
    """Minimal stand-in for ``starlette.requests.Request``."""

    def __init__(self, ip: str = "198.51.100.5") -> None:
        self.client = Namespace(host=ip)
        self.headers = {}


class TestEnforceRateLimit:
    async def test_rules_are_evaluated_in_order(self):
        store = InMemoryRateLimitStore()
        settings = Settings()
        settings.trust_proxy_headers = False
        request = FakeRequest()
        rules = [
            RateLimitRule(limit=2, scope="global"),
            RateLimitRule(limit=100, scope="music"),
        ]
        await enforce_rate_limit(request, store, None, rules, 60, settings)
        await enforce_rate_limit(request, store, None, rules, 60, settings)
        with pytest.raises(Exception) as excinfo:  # noqa: PT011
            await enforce_rate_limit(request, store, None, rules, 60, settings)
        # The first (global) bucket is the one that trips.
        assert excinfo.value.status_code == 429
        assert excinfo.value.headers["X-RateLimit-Scope"] == "global"

    async def test_user_identity_is_keyed_per_user(self):
        store = InMemoryRateLimitStore()
        settings = Settings()
        request = FakeRequest()
        rules = [RateLimitRule(limit=1, scope="global")]
        await enforce_rate_limit(request, store, "user-a", rules, 60, settings)
        with pytest.raises(Exception):  # noqa: B017, PT011
            await enforce_rate_limit(request, store, "user-a", rules, 60, settings)
        # Different user, different key: no 429.
        await enforce_rate_limit(request, store, "user-b", rules, 60, settings)

    async def test_anon_identity_is_keyed_per_ip(self):
        store = InMemoryRateLimitStore()
        settings = Settings()
        rules = [RateLimitRule(limit=1, scope="global")]
        await enforce_rate_limit(
            FakeRequest("1.1.1.1"), store, None, rules, 60, settings
        )
        with pytest.raises(Exception):  # noqa: B017, PT011
            await enforce_rate_limit(
                FakeRequest("1.1.1.1"), store, None, rules, 60, settings
            )
        await enforce_rate_limit(
            FakeRequest("2.2.2.2"), store, None, rules, 60, settings
        )

