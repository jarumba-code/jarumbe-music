"""Unit tests for the music search API route (``GET /api/v1/music/search``)."""

from __future__ import annotations

import pytest

from app.api.routes.music import get_jamendo_provider
from app.config import Settings, get_settings
from app.main import app

from tests.conftest import SAMPLE_SEARCH_RESPONSE


class TestSearchEndpoint:
    def test_search_success(self, client, success_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=afrobeats")
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "afrobeats"
            assert len(data["results"]) == 2
            assert data["results"][0]["title"] == "Afrobeats Fusion"
            assert data["results"][0]["provider"] == "jamendo"
            assert data["results"][0]["stream_url"] == "https://example.com/stream1.mp3"
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_query_stripped(self, client, success_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=%20%20afrobeats%20%20")
            assert response.status_code == 200
            assert response.json()["query"] == "afrobeats"
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_empty_query_rejected(self, client):
        # q="" passes FastAPI param-existence check but the route strips
        # and rejects empty/whitespace values with 400.
        response = client.get("/api/v1/music/search?q=")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_whitespace_query_rejected(self, client, success_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=%20%20%20")
            assert response.status_code == 400
            assert "empty" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_default_pagination(self, client, success_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=test")
            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == 20
            assert data["offset"] == 0
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_custom_pagination(self, client, success_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=test&limit=10&offset=5")
            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == 10
            assert data["offset"] == 5
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_provider_unavailable(self, client, error_provider):
        app.dependency_overrides[get_jamendo_provider] = lambda: error_provider
        try:
            response = client.get("/api/v1/music/search?q=test")
            assert response.status_code == 502
            assert "unavailable" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_search_missing_client_id(self, client):
        """When JAMENDO_CLIENT_ID is empty, the route returns 503."""
        mock_settings = Settings()
        mock_settings.jamendo_client_id = ""
        app.dependency_overrides[get_settings] = lambda: mock_settings
        try:
            response = client.get("/api/v1/music/search?q=test")
            assert response.status_code == 503
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_response_uses_jarumba_schema(self, client, success_provider):
        """Verify the response does NOT expose raw Jamendo fields."""
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=afrobeats")
            assert response.status_code == 200
            data = response.json()
            track = data["results"][0]
            # Jarumba normalised fields present
            for field in ("provider", "provider_track_id", "title", "artist",
                          "album", "duration", "artwork_url", "stream_url",
                          "download_url", "download_allowed", "license_url",
                          "license_name", "source_url", "release_date"):
                assert field in track, f"Missing field: {field}"
            # Raw Jamendo fields must NOT appear
            for jamendo_field in ("artist_idstr", "content_id_free", "waveform",
                                  "prourl", "position", "license_ccurl",
                                  "shorturl", "album_image", "audiodownload_allowed"):
                assert jamendo_field not in track, f"Unexpected raw field: {jamendo_field}"
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)

    def test_response_with_real_jamendo_fields(self, client, success_provider):
        """Verify license info is normalised from CC URL slug."""
        app.dependency_overrides[get_jamendo_provider] = lambda: success_provider
        try:
            response = client.get("/api/v1/music/search?q=afrobeats")
            track = response.json()["results"][0]
            assert track["license_url"] == "http://creativecommons.org/licenses/by-nc-nd/3.0/"
            assert track["license_name"] == "CC BY-NC-ND"
            assert track["download_allowed"] is True
        finally:
            app.dependency_overrides.pop(get_jamendo_provider, None); app.dependency_overrides.pop(get_settings, None)
