"""Rate limiting for the Jarumba API.

Design (see docs/security.md):

* Fixed-window counters with a 60-second window.
* **Distributed by default**: counters live in Redis (``REDIS_URL``) so the
  limit is enforced consistently across all FastAPI replicas.  The in-process
  store exists only as a single-replica local-dev fallback and for tests; a
  deployed environment fails fast instead of silently degrading to it
  (:func:`require_shared_rate_limit_backend`).
* **Key choice**: authenticated requests are keyed by the verified user UUID
  (never by IP — mobile users commonly share NAT addresses); unauthenticated
  requests are keyed by client IP.  Forwarding headers are only honoured for
  peers listed in ``TRUSTED_PROXY_IPS`` (see :func:`client_ip`).
* **Failure policy**: Redis outages fail *open* for normal browsing endpoints
  (a temporary outage must not take the API down) and fail *closed* for
  authentication endpoints (an attacker must not be able to bypass auth
  rate limits by knocking Redis over).
* Responses include ``Retry-After`` and ``X-RateLimit-Limit`` /
  ``X-RateLimit-Remaining`` headers, and use the same ``{"detail": ...}`` JSON
  error shape as every other API error.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import Settings, get_settings

# Bounds on the client-supplied forwarding header: a huge or absurdly long
# ``X-Forwarded-For`` value is ignored outright rather than parsed.
_FORWARDED_FOR_MAX_LENGTH = 1024
_FORWARDED_FOR_MAX_HOPS = 32



class RateLimitStore:
    """Fixed-window counter backend interface."""

    async def increment(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Increment ``key``; return ``(count, seconds_until_window_reset)``."""
        raise NotImplementedError


class InMemoryRateLimitStore(RateLimitStore):
    """Process-local counters — single-replica dev/test fallback ONLY.

    Not the production source of truth; with multiple replicas each process
    would enforce its own (weaker) limits, which is why ``REDIS_URL`` should
    always be set in deployed environments.
    """

    def __init__(self) -> None:
        self._counters: dict[str, tuple[int, float]] = {}

    async def increment(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = time.monotonic()
        count, window_start = self._counters.get(key, (0, now))
        if now - window_start >= window_seconds:
            count, window_start = 0, now
        count += 1
        self._counters[key] = (count, window_start)
        reset_in = int(window_seconds - (now - window_start)) + 1
        return count, reset_in


class RedisRateLimitStore(RateLimitStore):
    """Redis-backed fixed-window counters (multi-replica safe).

    ``INCR`` and the first-write ``EXPIRE`` are executed as **one** atomic Lua
    script.  Issuing them as two separate commands would leave a window in
    which a crash (or a second replica) can strand the counter without a TTL;
    the script makes the increment-and-expiry pair indivisible.

    Connect and read/write timeouts are explicit so an unresponsive Redis can
    never hold a request open indefinitely.
    """

    #: KEYS[1] = counter key, ARGV[1] = TTL in seconds.
    INCREMENT_SCRIPT = (
        "local current = redis.call('INCR', KEYS[1]) "
        "if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end "
        "return current"
    )

    def __init__(
        self,
        redis_url: str,
        *,
        connect_timeout: float = 1.0,
        command_timeout: float = 1.0,
        client: object | None = None,
    ) -> None:
        self._redis = client or aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_timeout,
            socket_timeout=command_timeout,
            health_check_interval=30,
        )

    @property
    def client(self) -> object:
        """The underlying Redis client (exposed for health checks/tests)."""
        return self._redis

    async def increment(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = int(time.time())
        window_start = now - (now % window_seconds)
        redis_key = f"ratelimit:{key}:{window_start}"
        # One round-trip, one atomic script: count and expiry can never drift.
        count = await self._redis.eval(
            self.INCREMENT_SCRIPT, 1, redis_key, str(window_seconds + 1)
        )
        reset_in = window_start + window_seconds - now + 1
        return int(count), reset_in


@dataclass
class RateLimitRule:
    """One rate-limit bucket."""

    limit: int
    scope: str  # bucket name, e.g. "music"
    fail_closed: bool = False


def _is_trusted_proxy(peer: str, trusted: list[str]) -> bool:
    """True when *peer* is an explicitly configured trusted reverse proxy."""
    if not peer:
        return False
    peer_address = None
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        peer_address = None

    for entry in trusted:
        if entry == peer:
            return True
        if peer_address is None:
            continue
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if peer_address in network:
            return True
    return False


def _normalise_ip(candidate: str) -> str | None:
    """Return a canonical IP string, or ``None`` when *candidate* is not an IP."""
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request: Request, settings: Settings | None = None) -> str:
    """Best-effort client IP for anonymous rate limiting.

    ``X-Forwarded-For`` is a **client-controlled** header, so it is only
    consulted when *both* conditions hold:

    * ``TRUST_PROXY_HEADERS`` is explicitly enabled, and
    * the immediate peer (as reported by ASGI) is listed in
      ``TRUSTED_PROXY_IPS``.

    Otherwise the direct peer address is used, which means a spoofed
    forwarding header cannot mint a fresh rate-limit bucket.  The
    ``TRUSTED_PROXY_COUNT`` right-hand hops are skipped, the value is parsed as
    a real IP address, and any unusable value falls back to the peer.
    """
    settings = settings or get_settings()
    peer = request.client.host if request.client else "unknown"

    if not settings.trust_proxy_headers:
        return peer
    if not _is_trusted_proxy(peer, settings.trusted_proxies):
        return peer

    raw = request.headers.get("x-forwarded-for")
    if not raw or len(raw) > _FORWARDED_FOR_MAX_LENGTH:
        return peer

    hops = [hop.strip() for hop in raw.split(",") if hop.strip()]
    if not hops:
        return peer
    hops = hops[-_FORWARDED_FOR_MAX_HOPS:]

    index = len(hops) - max(settings.trusted_proxy_count, 1)
    if index < 0:
        index = 0
    return _normalise_ip(hops[index]) or peer


async def enforce_rate_limit(
    request: Request,
    store: RateLimitStore,
    user_id: str | None,
    rules: list[RateLimitRule],
    window_seconds: int,
    settings: Settings | None = None,
) -> None:
    """Check every applicable bucket; raise 429 on the first exceeded one.

    Rules are evaluated in order (global bucket first, then the endpoint
    bucket) and *every* applicable counter is incremented for the request, so
    the interaction between the global and per-endpoint buckets is
    deterministic: exceeding a later bucket still consumes the earlier one.

    Keys: ``global:anon:<ip>`` / ``global:auth:<user>``, and per-rule
    ``<scope>:anon:<ip>`` / ``<scope>:auth:<user>``.
    """
    settings = settings or get_settings()
    ip = client_ip(request, settings)

    for rule in rules:
        identity = f"auth:{user_id}" if user_id is not None else f"anon:{ip}"
        key = f"{rule.scope}:{identity}"

        try:
            count, reset_in = await store.increment(key, window_seconds)
        except Exception:
            # Redis/store outage: fail open or closed per endpoint policy.
            if rule.fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting service unavailable",
                ) from None
            continue

        if count > rule.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(max(reset_in, 1)),
                    "X-RateLimit-Limit": str(rule.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Scope": rule.scope,
                },
            )


def require_shared_rate_limit_backend(settings: Settings | None = None) -> None:
    """Fail fast instead of silently using per-process counters.

    Raises :class:`RuntimeError` when a deployed environment has no
    ``REDIS_URL`` and has not explicitly acknowledged the risk with
    ``RATE_LIMIT_ALLOW_MEMORY_FALLBACK=true``.  Development/local/test
    environments keep the in-process fallback.
    """
    settings = settings or get_settings()
    if (settings.redis_url or "").strip():
        return
    if settings.rate_limit_allow_memory_fallback or settings.is_local_environment:
        return
    raise RuntimeError(
        "REDIS_URL is required in a deployed environment: process-local "
        "rate-limit counters are per-replica and must never be a silent "
        "fallback.  Set REDIS_URL, or set "
        "RATE_LIMIT_ALLOW_MEMORY_FALLBACK=true to accept weaker limits."
    )


def build_rate_limit_store(settings: Settings | None = None) -> RateLimitStore:
    """Construct the configured limiter backend (Redis when available)."""
    settings = settings or get_settings()
    require_shared_rate_limit_backend(settings)

    redis_url = (settings.redis_url or "").strip()
    if redis_url:
        return RedisRateLimitStore(
            redis_url,
            connect_timeout=settings.redis_connect_timeout_seconds,
            command_timeout=settings.redis_command_timeout_seconds,
        )
    return InMemoryRateLimitStore()
