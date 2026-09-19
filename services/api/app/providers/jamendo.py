"""Jamendo music provider (API v3.0).

Jamendo's v3.0 REST API is the currently supported public endpoint.  The
v3.1 path advertised in some older documentation is **not** served by the
API gateway and returns a generic "method not found" error, so we target
v3.0 directly.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from app.providers.base import (
    BaseProvider,
    ProviderResponseError,
    ProviderUnavailableError,
    Track,
)

JAMENDO_API_BASE = "https://api.jamendo.com/v3.0"
JAMENDO_DEFAULT_TIMEOUT = 15.0
JAMENDO_DEFAULT_LIMIT = 20
JAMENDO_MAX_LIMIT = 50
JAMENDO_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
JAMENDO_MAX_RETRIES = 2
JAMENDO_RETRY_BACKOFF_SECONDS = 0.1

_shared_http_client: httpx.AsyncClient | None = None


def _shared_client(timeout: float) -> httpx.AsyncClient:
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0), write=min(timeout, 5.0)),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_http_client

# ---------------------------------------------------------------------------
# License helpers
# ---------------------------------------------------------------------------

# Mapping from the slug inside a CC license URL to a short, human-readable
# name.  Only the most common Creative Commons variants are listed; any
# unknown slug is left as-is (the raw URL is always preserved separately
# in ``license_url``).
_LICENSE_SLUGS: dict[str, str] = {
    "cc0": "CC0",
    "public-domain": "Public Domain",
    "by": "CC BY",
    "by-sa": "CC BY-SA",
    "by-nc": "CC BY-NC",
    "by-nc-sa": "CC BY-NC-SA",
    "by-nd": "CC BY-ND",
    "by-nc-nd": "CC BY-NC-ND",
}


def _extract_license(
    license_ccurl: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Extract a (license_url, license_name) pair from Jamendo's ``license_ccurl``.

    Jamendo stores the Creative Commons URL in ``license_ccurl``.  When the
    field is empty or absent both return values are ``None``.
    """
    if not license_ccurl:
        return None, None

    license_url = license_ccurl.strip()

    # Match a known CC license slug anywhere in the URL, e.g.
    # http://creativecommons.org/licenses/by-nc-nd/3.0/
    # Iterate in descending-length order so that "by-nc-nd" is matched
    # before "by" (which is a substring of every CC BY-* slug).
    for slug in sorted(_LICENSE_SLUGS, key=len, reverse=True):
        if slug in license_url:
            return license_url, _LICENSE_SLUGS[slug]

    # Unknown license -- preserve the URL but leave the name unset.
    return license_url, None


class JamendoProvider(BaseProvider):
    """Music provider backed by the Jamendo REST API (v3.0).

    Parameters
    ----------
    client_id
        Jamendo API client ID (read from ``JAMENDO_CLIENT_ID``).
    timeout
        Per-request timeout in seconds.
    http_client
        Optional pre-configured :class:`httpx.AsyncClient`.  When omitted a
        new client is created for each request.  Primarily for testing
        (inject an :class:`httpx.MockTransport`) but also allows callers to
        share a client with a connection pool in production.
    """

    def __init__(
        self,
        client_id: str,
        timeout: float = JAMENDO_DEFAULT_TIMEOUT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not client_id or not client_id.strip():
            raise ValueError("client_id must not be empty")
        self.client_id = client_id
        self.timeout = timeout
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "jamendo"

    async def search_tracks(
        self,
        query: str,
        limit: int = JAMENDO_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> list[Track]:
        params = {
            "client_id": self.client_id,
            "format": "json",
            "search": query,
            "limit": min(limit, JAMENDO_MAX_LIMIT),
            "offset": offset,
        }
        raw = await self._request("tracks/", params)
        results = raw.get("results", [])
        if not isinstance(results, list):
            raise ProviderResponseError(
                "Unexpected Jamendo response: results is not a list"
            )
        return [self.normalize(item) for item in results]

    async def get_track(self, provider_track_id: str) -> Optional[Track]:
        params = {
            "client_id": self.client_id,
            "format": "json",
            "limit": 1,
            "id": provider_track_id,
        }
        raw = await self._request("tracks/", params)
        results = raw.get("results", [])
        if not isinstance(results, list):
            raise ProviderResponseError(
                "Unexpected Jamendo response: results is not a list"
            )
        if not results:
            return None
        return self.normalize(results[0])

    @staticmethod
    def normalize(raw: dict) -> Track:
        """Convert a raw Jamendo track dict into Jarumba's :class:`Track`."""
        if not isinstance(raw, dict):
            raise ProviderResponseError(
                f"Expected a dict track object, got {type(raw).__name__}"
            )

        license_url, license_name = _extract_license(raw.get("license_ccurl"))

        return Track(
            provider="jamendo",
            provider_track_id=str(raw.get("id", "")),
            title=raw.get("name", ""),
            artist=raw.get("artist_name", ""),
            album=raw.get("album_name") or None,
            duration=raw.get("duration"),
            artwork_url=raw.get("album_image") or raw.get("image"),
            stream_url=raw.get("audio"),
            download_url=raw.get("audiodownload"),
            download_allowed=bool(raw.get("audiodownload_allowed", False)),
            license_url=license_url,
            license_name=license_name,
            source_url=raw.get("shareurl") or raw.get("url") or raw.get("shorturl"),
            release_date=raw.get("releasedate"),
        )

    # ------------------------------------------------------------------ #
    #  Internal HTTP helpers                                             #
    # ------------------------------------------------------------------ #

    async def _request(self, path: str, params: dict) -> dict:
        """Perform a GET request to the Jamendo API and return parsed JSON.

        Raises
        ------
        ProviderUnavailableError
            On network failure, timeout, or non-200 HTTP status.
        ProviderResponseError
            When the response body is not valid JSON or has an unexpected
            top-level structure.
        """
        url = f"{JAMENDO_API_BASE}/{path.lstrip('/')}"

        try:
            client = self._http_client or _shared_client(self.timeout)
            for attempt in range(JAMENDO_MAX_RETRIES + 1):
                try:
                    resp = await client.get(url, params=params)
                except asyncio.CancelledError:
                    raise
                except httpx.TimeoutException as exc:
                    if attempt >= JAMENDO_MAX_RETRIES:
                        raise ProviderUnavailableError(
                            "Jamendo request timed out"
                        ) from exc
                    await asyncio.sleep(JAMENDO_RETRY_BACKOFF_SECONDS * (2**attempt))
                except httpx.HTTPError as exc:
                    if attempt >= JAMENDO_MAX_RETRIES:
                        raise ProviderUnavailableError(
                            f"Jamendo HTTP error: {type(exc).__name__}"
                        ) from exc
                    await asyncio.sleep(JAMENDO_RETRY_BACKOFF_SECONDS * (2**attempt))
                else:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        if attempt < JAMENDO_MAX_RETRIES:
                            await asyncio.sleep(
                                JAMENDO_RETRY_BACKOFF_SECONDS * (2**attempt)
                            )
                            continue
                    break
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                "Jamendo request timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Jamendo HTTP error: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            raise ProviderUnavailableError(
                f"Jamendo returned HTTP {resp.status_code}"
            )

        if len(resp.content) > JAMENDO_MAX_RESPONSE_BYTES:
            raise ProviderResponseError("Jamendo response exceeded the allowed size")

        try:
            data = resp.json()
        except Exception:
            raise ProviderResponseError(
                "Jamendo returned an invalid JSON response"
            )

        if not isinstance(data, dict):
            raise ProviderResponseError(
                "Unexpected Jamendo response: expected a JSON object"
            )

        # Check for Jamendo-level errors in the response headers.
        # Do NOT leak internal error messages or credentials.
        headers = data.get("headers", {})
        if isinstance(headers, dict) and headers.get("status") == "failed":
            raise ProviderUnavailableError(
                "Jamendo API reported a server-side error"
            )

        return data

