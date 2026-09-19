"""Short-lived cache for provider search results.

Scope and safety rules (see docs/architecture.md):

* **Only** public search metadata is cached.  Never passwords, refresh tokens,
  private user data, favorites/playlists/history (they are the source of truth
  in PostgreSQL), or provider secrets.
* Keys are deterministic and include the provider identity, the normalised
  query and the pagination window, so two different searches can never share an
  entry.
* The TTL is deliberately short (``SEARCH_CACHE_TTL_SECONDS``, default 60s).
  Stream/download URLs are treated as ephemeral: a provider whose URLs are
  short-lived (for example signed URLs) declares
  ``cacheable_stream_urls=False`` in :mod:`app.providers.registry` and those
  fields are stripped before the payload is stored.
* Redis being down is never fatal for browsing: read/write failures are
  swallowed (fail-open) and the request falls back to the provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

import redis.asyncio as aioredis

from app.config import Settings, get_settings
from app.providers.registry import provider_spec

logger = logging.getLogger("jarumba.cache")

#: Bump when the cached payload shape changes.
CACHE_KEY_VERSION = "v1"

#: Fields that must never be cached for providers with short-lived URLs.
_EPHEMERAL_URL_FIELDS = ("stream_url", "download_url")


class SearchCache(Protocol):
    """Async key/value cache for search payloads."""

    async def get(self, key: str) -> Any | None:
        """Return the cached JSON value, or ``None`` on a miss."""

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store *value* under *key* for at most *ttl_seconds*."""


class NullSearchCache:
    """No-op cache used when Redis is not configured (and in tests)."""

    async def get(self, key: str) -> Any | None:  # noqa: D102 - protocol method
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:  # noqa: D102
        return None


class RedisSearchCache:
    """Redis-backed cache with explicit connect/command timeouts."""

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
        """The underlying Redis client (exposed for tests)."""
        return self._redis

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            # Corrupt/legacy entry: treat as a miss rather than failing.
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        await self._redis.set(key, payload, ex=max(int(ttl_seconds), 1))


def build_search_cache(settings: Settings | None = None) -> SearchCache:
    """Redis cache when ``REDIS_URL`` is set, otherwise a no-op cache."""
    settings = settings or get_settings()
    redis_url = (settings.redis_url or "").strip()
    if not redis_url:
        return NullSearchCache()
    return RedisSearchCache(
        redis_url,
        connect_timeout=settings.redis_connect_timeout_seconds,
        command_timeout=settings.redis_command_timeout_seconds,
    )


def search_cache_key(
    *, provider: str, query: str, limit: int, offset: int
) -> str:
    """Deterministic cache key for one provider search window."""
    digest = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:32]
    return f"search:{CACHE_KEY_VERSION}:{provider}:{digest}:{limit}:{offset}"


def cacheable_search_payload(payload: list[dict], *, provider: str) -> list[dict]:
    """Strip fields that must not be cached for this provider.

    Providers that hand out short-lived (signed) stream URLs are registered
    with ``cacheable_stream_urls=False``; for them the URL fields are removed
    from the cached copy so a stale URL can never be served from the cache.
    """
    if provider_spec(provider).cacheable_stream_urls:
        return payload
    return [
        {k: v for k, v in item.items() if k not in _EPHEMERAL_URL_FIELDS}
        for item in payload
    ]


async def cache_get(cache: SearchCache, key: str) -> Any | None:
    """Fail-open read: a cache outage must never break a search request."""
    try:
        return await cache.get(key)
    except Exception as exc:  # noqa: BLE001 - any cache failure degrades to a miss
        logger.debug("event=search_cache_read_failed error=%s", type(exc).__name__)
        return None


async def cache_set(cache: SearchCache, key: str, value: Any, ttl_seconds: int) -> None:
    """Fail-open write: caching is an optimization, never a requirement."""
    try:
        await cache.set(key, value, ttl_seconds)
    except Exception as exc:  # noqa: BLE001 - a failed write must not fail the request
        logger.debug("event=search_cache_write_failed error=%s", type(exc).__name__)


__all__ = [
    "CACHE_KEY_VERSION",
    "NullSearchCache",
    "RedisSearchCache",
    "SearchCache",
    "build_search_cache",
    "cache_get",
    "cache_set",
    "cacheable_search_payload",
    "search_cache_key",
]