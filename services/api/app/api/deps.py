"""Shared FastAPI dependencies: optional identity + per-route rate limits."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Query, Request
from fastapi.security.utils import get_authorization_scheme_param

from app.config import Settings, get_settings
from app.services.auth import _jwks_client_for, verify_supabase_token, verify_supabase_token_jwks
from app.services.cache import SearchCache, build_search_cache
from app.services.rate_limit import (
    RateLimitRule,
    RateLimitStore,
    build_rate_limit_store,
    enforce_rate_limit,
)


@lru_cache(maxsize=1)
def get_search_cache() -> SearchCache:
    """One search cache per process (Redis-backed when REDIS_URL is set).

    Redis failures are non-fatal: every access in the music route is fail-open,
    so an outage degrades to provider calls instead of errors.
    """
    return build_search_cache(get_settings())


@lru_cache(maxsize=1)
def get_rate_limit_store() -> RateLimitStore:
    """One limiter backend per process.

    Redis when REDIS_URL is configured (multi-replica safe); in-process
    (see app.services.rate_limit.require_shared_rate_limit_backend).
    """
    return build_rate_limit_store(get_settings())


def get_optional_user_id(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Return the verified user UUID when a valid Bearer token is present.

    Any verification failure (or absent token) yields None - the request
    then falls into the anonymous rate-limit buckets.  The returned value
    comes only from the verified JWT; a user_id in a body/query/path can
    never influence the rate-limit identity.
    """
    raw = request.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(raw)
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        if settings.supabase_url:
            claims = verify_supabase_token_jwks(
                token=token,
                jwks_client=_jwks_client_for(settings.supabase_url),
                audience=settings.supabase_url,
            )
        elif settings.supabase_jwt_secret:
            claims = verify_supabase_token(
                token=token,
                secret=settings.supabase_jwt_secret,
                audience=settings.supabase_url,
            )
        else:
            return None
    except Exception:  # noqa: BLE001 - any invalid token is just "anonymous"
        return None
    return str(claims.get("sub") or "")


def rate_limiter(scope: str, fail_closed: bool = False):
    """Build a dependency enforcing the global bucket plus one scope bucket.

    The endpoint-specific limit is read from
    ``settings.rate_limit_<scope>_per_minute``.

    Attach this on the route decorator (``dependencies=[Depends(...)]``):
    FastAPI resolves decorator-level dependencies *before* the endpoint's own
    parameters, which is exactly what makes rate limiting run before JWT
    verification.  An invalid / expired / unknown-``kid`` / malformed token
    therefore cannot be used to bypass the limiter — it is charged to the
    anonymous (IP) bucket instead.
    """

    async def _dependency(
        request: Request,
        user_id: str | None = Depends(get_optional_user_id),
        settings: Settings = Depends(get_settings),
        store: RateLimitStore = Depends(get_rate_limit_store),
    ) -> None:
        limit = getattr(settings, f"rate_limit_{scope}_per_minute", None)
        rules: list[RateLimitRule] = [
            RateLimitRule(
                limit=(
                    settings.rate_limit_global_auth_per_minute
                    if user_id
                    else settings.rate_limit_global_anon_per_minute
                ),
                scope="global",
            )
        ]
        if limit is not None:
            rules.append(
                RateLimitRule(limit=limit, scope=scope, fail_closed=fail_closed)
            )
        await enforce_rate_limit(
            request,
            store,
            user_id,
            rules,
            settings.rate_limit_window_seconds,
            settings,
        )

    return _dependency


class PaginationParams:
    """Shared limit/offset query-parameter validation.

    Both values are bounds-checked server-side so no endpoint can be asked
    for an unbounded result set.
    """

    def __init__(
        self,
        limit: int = Query(50, ge=1, le=100, description="Page size (1-100)"),
        offset: int = Query(0, ge=0, description="Number of rows to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset
