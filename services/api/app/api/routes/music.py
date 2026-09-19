"""Music search routes.

These endpoints delegate to the provider layer.  The route layer is
responsible for:

* Input validation (bounded query length, pagination bounds).
* Error translation (provider errors → HTTP status codes).
* Short-lived caching of the normalised metadata (stream URLs are excluded for
  providers that declare them ephemeral).
* Serialising provider :class:`~app.providers.base.Track` objects into the
  public :class:`~app.schemas.music.TrackResponse` schema.

The provider implementation is resolved through :mod:`app.providers.registry`,
the single server-side allow-list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_search_cache, rate_limiter
from app.config import Settings, get_settings
from app.providers.base import BaseProvider, ProviderUnavailableError
from app.providers.registry import MusicProvider, build_provider
from app.schemas.music import SearchResponse, TrackResponse
from app.services.cache import (
    SearchCache,
    cache_get,
    cache_set,
    cacheable_search_payload,
    search_cache_key,
)

router = APIRouter()


def get_jamendo_provider(
    settings: Settings = Depends(get_settings),
) -> BaseProvider:
    """FastAPI dependency that builds the active provider from settings.

    Construction goes through :func:`app.providers.registry.build_provider`, so
    the registry remains the single place that maps a provider name to an
    implementation.
    """
    if not settings.jamendo_client_id:
        raise HTTPException(
            status_code=503,
            detail="Music provider is not configured",
        )
    return build_provider(MusicProvider.JAMENDO.value, settings)


@router.get(
    "/music/search",
    response_model=SearchResponse,
    dependencies=[Depends(rate_limiter("music"))],
)
async def search_music(
    q: str = Query(..., description="Search query (see MUSIC_SEARCH_MAX_QUERY_LENGTH)"),
    limit: int = Query(default=20, ge=1, le=50, description="Max results (1-50)"),
    offset: int = Query(default=0, ge=0, description="Result offset for pagination"),
    provider: BaseProvider = Depends(get_jamendo_provider),
    cache: SearchCache = Depends(get_search_cache),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    """Search for tracks on the active music provider.

    Status codes:

    * ``200`` — normalised results (possibly served from a short-lived cache).
    * ``400`` — the query is empty or whitespace-only.
    * ``422`` — the query is longer than ``MUSIC_SEARCH_MAX_QUERY_LENGTH``
      (a controlled validation error: the value is never silently truncated).
    * ``429`` — rate limit exceeded (30/minute by default).
    * ``502`` — the provider is temporarily unavailable.
    * ``503`` — the provider is not configured (missing credential).
    """
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Query must not be empty or whitespace-only",
        )

    max_query_length = settings.music_search_max_query_length
    if len(query) > max_query_length:
        raise HTTPException(
            status_code=422,
            detail=f"Query must be at most {max_query_length} characters",
        )

    cache_key = search_cache_key(
        provider=provider.name, query=query, limit=limit, offset=offset
    )
    cached = await cache_get(cache, cache_key)
    if isinstance(cached, list):
        # Cache hits are normalised metadata only — the public contract is
        # identical to a fresh provider response.
        return SearchResponse(
            query=query,
            limit=limit,
            offset=offset,
            total=len(cached),
            results=[TrackResponse(**item) for item in cached],
        )

    try:
        tracks = await provider.search_tracks(query=query, limit=limit, offset=offset)
    except ProviderUnavailableError:
        raise HTTPException(
            status_code=502,
            detail="Music provider is temporarily unavailable",
        )

    results = [TrackResponse.from_track(t) for t in tracks]
    await cache_set(
        cache,
        cache_key,
        cacheable_search_payload(
            [item.model_dump(mode="json") for item in results],
            provider=provider.name,
        ),
        settings.search_cache_ttl_seconds,
    )

    return SearchResponse(
        query=query,
        limit=limit,
        offset=offset,
        total=len(results),
        results=results,
    )
