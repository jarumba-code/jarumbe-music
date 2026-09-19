"""Unit tests for the Jamendo provider layer.

All external Jamendo HTTP calls are mocked via :class:`httpx.MockTransport`
so the tests never touch the live API.
"""

from __future__ import annotations

import httpx
import pytest

from app.providers.base import (
    ProviderResponseError,
    ProviderUnavailableError,
    Track,
)
from app.providers.jamendo import JamendoProvider

from tests.conftest import (
    SAMPLE_TRACK_RAW,
    SAMPLE_TRACK_RAW_NO_LICENSE,
)


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------

class TestProviderConstruction:
    def test_requires_client_id(self):
        with pytest.raises(ValueError, match="client_id"):
            JamendoProvider(client_id="")

    def test_requires_non_whitespace_client_id(self):
        with pytest.raises(ValueError, match="client_id"):
            JamendoProvider(client_id="   ")

    def test_name_property(self):
        provider = JamendoProvider(client_id="abc123")
        assert provider.name == "jamendo"

    def test_default_timeout(self):
        provider = JamendoProvider(client_id="abc123")
        assert provider.timeout == 15.0


# ---------------------------------------------------------------------------
# Normalise / Track mapping
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_normalize_full_track(self):
        track = JamendoProvider.normalize(SAMPLE_TRACK_RAW)
        assert track.provider == "jamendo"
        assert track.provider_track_id == "12345"
        assert track.title == "Afrobeats Fusion"
        assert track.artist == "Silver-Stage"
        assert track.album == "Test Album"
        assert track.duration == 200
        assert track.artwork_url == "https://example.com/art1.jpg"
        assert track.stream_url == "https://example.com/stream1.mp3"
        assert track.download_url == "https://example.com/download1.mp3"
        assert track.download_allowed is True
        assert track.license_url == "http://creativecommons.org/licenses/by-nc-nd/3.0/"
        assert track.license_name == "CC BY-NC-ND"
        assert track.source_url == "https://www.jamendo.com/track/12345"
        assert track.release_date == "2020-01-01"

    def test_normalize_no_license(self):
        track = JamendoProvider.normalize(SAMPLE_TRACK_RAW_NO_LICENSE)
        assert track.license_url is None
        assert track.license_name is None
        assert track.download_allowed is False

    def test_normalize_album_image_preferred_over_image(self):
        raw = dict(SAMPLE_TRACK_RAW)
        raw["album_image"] = "https://example.com/album.jpg"
        raw["image"] = "https://example.com/generic.jpg"
        track = JamendoProvider.normalize(raw)
        assert track.artwork_url == "https://example.com/album.jpg"

    def test_normalize_falls_back_to_image(self):
        raw = dict(SAMPLE_TRACK_RAW)
        raw.pop("album_image")
        raw["image"] = "https://example.com/fallback.jpg"
        track = JamendoProvider.normalize(raw)
        assert track.artwork_url == "https://example.com/fallback.jpg"

    def test_normalize_source_url_priority(self):
        raw = dict(SAMPLE_TRACK_RAW)
        raw["shareurl"] = "https://share.example.com"
        raw["url"] = "https://url.example.com"
        raw["shorturl"] = "https://short.example.com"
        track = JamendoProvider.normalize(raw)
        assert track.source_url == "https://share.example.com"

    def test_normalize_minimal_fields(self):
        track = JamendoProvider.normalize({"id": "1", "name": "T", "artist_name": "A"})
        assert track.provider == "jamendo"
        assert track.provider_track_id == "1"
        assert track.title == "T"
        assert track.artist == "A"
        assert track.album is None
        assert track.duration is None
        assert track.stream_url is None
        assert track.download_allowed is False

    def test_normalize_invalid_input(self):
        with pytest.raises(ProviderResponseError):
            JamendoProvider.normalize("not a dict")  # type: ignore[arg-type]
        with pytest.raises(ProviderResponseError):
            JamendoProvider.normalize(None)  # type: ignore[arg-type]

    def test_normalize_id_always_string(self):
        track = JamendoProvider.normalize({"id": 12345, "name": "T", "artist_name": "A"})
        assert track.provider_track_id == "12345"


# ---------------------------------------------------------------------------
# License extraction
# ---------------------------------------------------------------------------

class TestLicenseExtraction:
    @pytest.mark.parametrize(
        "ccurl,expected_name",
        [
            ("http://creativecommons.org/licenses/by-sa/3.0/", "CC BY-SA"),
            ("http://creativecommons.org/licenses/by-nc-nd/3.0/", "CC BY-NC-ND"),
            ("http://creativecommons.org/licenses/by/4.0/", "CC BY"),
            ("http://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA"),
            ("http://creativecommons.org/licenses/by-nd/3.0/", "CC BY-ND"),
            ("http://creativecommons.org/licenses/cc0/1.0/", "CC0"),
            ("http://example.com/unknown", None),
            ("", None),
        ],
    )
    def test_license_names(self, ccurl, expected_name):
        track = JamendoProvider.normalize(
            {"id": "1", "name": "T", "artist_name": "A", "license_ccurl": ccurl}
        )
        assert track.license_name == expected_name
        if ccurl:
            assert track.license_url == ccurl
        else:
            assert track.license_url is None


# ---------------------------------------------------------------------------
# search_tracks
# ---------------------------------------------------------------------------

class TestSearchTracks:
    async def test_search_uses_broad_search_parameter(self):
        captured = {}

        async def handler(request):
            captured.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "headers": {"status": "success", "code": 0},
                    "results": [SAMPLE_TRACK_RAW],
                },
                request=request,
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = JamendoProvider(client_id="test", http_client=client)
        try:
            tracks = await provider.search_tracks("afrobeats", limit=20, offset=0)
        finally:
            await client.aclose()

        assert tracks[0].title == "Afrobeats Fusion"
        assert captured["search"] == "afrobeats"
        assert captured["limit"] == "20"
        assert captured["offset"] == "0"
        assert "name" not in captured

    async def test_search_returns_normalised_tracks(self, success_provider):
        tracks = await success_provider.search_tracks("afrobeats")
        assert len(tracks) == 2
        assert all(isinstance(t, Track) for t in tracks)
        assert tracks[0].title == "Afrobeats Fusion"
        assert tracks[0].provider == "jamendo"
        assert tracks[1].title == "No License Track"

    async def test_search_empty_results(self, empty_provider):
        tracks = await empty_provider.search_tracks("nonexistent")
        assert tracks == []

    async def test_search_limit_capped(self, mock_http_factory):
        raw = {
            "headers": {"status": "success", "code": 0},
            "results": [],
        }
        http_client = mock_http_factory(raw)
        provider = JamendoProvider(client_id="test", http_client=http_client)
        await provider.search_tracks("test", limit=100, offset=0)

    async def test_search_http_error_raises_unavailable(self, http_error_provider):
        with pytest.raises(ProviderUnavailableError):
            await http_error_provider.search_tracks("test")

    async def test_search_jamendo_error_raises_unavailable(self, error_provider):
        with pytest.raises(ProviderUnavailableError):
            await error_provider.search_tracks("test")

    async def test_search_malformed_json_raises_response_error(self, malformed_provider):
        with pytest.raises(ProviderResponseError):
            await malformed_provider.search_tracks("test")

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    async def test_retryable_status_is_retried_with_a_bound(self, status_code):
        attempts = 0

        async def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                return httpx.Response(status_code, request=request)
            return httpx.Response(
                200,
                json={"headers": {"status": "success"}, "results": [],},
                request=request,
            )

        provider = JamendoProvider(
            client_id="test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            assert await provider.search_tracks("test") == []
        finally:
            await provider._http_client.aclose()
        assert attempts == 3

    async def test_retryable_failure_is_bounded(self):
        attempts = 0

        async def handler(request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, request=request)

        provider = JamendoProvider(
            client_id="test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            with pytest.raises(ProviderUnavailableError):
                await provider.search_tracks("test")
        finally:
            await provider._http_client.aclose()
        assert attempts == 3

    async def test_oversized_response_is_rejected(self):
        async def handler(request):
            return httpx.Response(
                200,
                content=b"{" + b"x" * (2 * 1024 * 1024) + b"}",
                request=request,
            )

        provider = JamendoProvider(
            client_id="test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            with pytest.raises(ProviderResponseError, match="exceeded"):
                await provider.search_tracks("test")
        finally:
            await provider._http_client.aclose()


# ---------------------------------------------------------------------------
# get_track
# ---------------------------------------------------------------------------

class TestGetTrack:
    async def test_get_track_found(self, mock_http_factory):
        response = {
            "headers": {"status": "success", "code": 0},
            "results": [SAMPLE_TRACK_RAW],
        }
        http_client = mock_http_factory(response)
        provider = JamendoProvider(client_id="test", http_client=http_client)
        track = await provider.get_track("12345")
        assert track is not None
        assert track.title == "Afrobeats Fusion"

    async def test_get_track_not_found(self, mock_http_factory):
        response = {"headers": {"status": "success", "code": 0}, "results": []}
        http_client = mock_http_factory(response)
        provider = JamendoProvider(client_id="test", http_client=http_client)
        track = await provider.get_track("999999")
        assert track is None

    async def test_get_track_malformed_raises(self, malformed_provider):
        with pytest.raises(ProviderResponseError):
            await malformed_provider.get_track("12345")

