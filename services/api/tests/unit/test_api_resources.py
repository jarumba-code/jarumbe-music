"""Endpoint tests for profiles, favorites, playlists, tracks, and history.

Every test runs against the shared :mod:`tests.unit.api_testbed` (in-memory
SQLite + in-process limiter + deterministic HS256 settings).  The suite
covers success paths, unauthenticated access, IDOR attempts, duplicate
handling, validation errors, pagination caps, and not-found behavior.
"""

from __future__ import annotations

import uuid as uuid_mod

import pytest

from tests.unit.api_testbed import USER_A, USER_B, api  # noqa: F401  register fixture

TRACK = {
    "provider": "jamendo",
    "provider_track_id": "tr-1",
    "title": "Song",
    "artist": "Artist",
}


def _new_id() -> str:
    return str(uuid_mod.uuid4())


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


class TestUnauthenticated:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/profile"),
            ("PATCH", "/api/v1/profile"),
            ("GET", "/api/v1/favorites"),
            ("POST", "/api/v1/favorites"),
            ("GET", "/api/v1/playlists"),
            ("POST", "/api/v1/playlists"),
            ("GET", "/api/v1/recently-played"),
            ("POST", "/api/v1/recently-played"),
        ],
    )
    def test_requires_bearer_token(self, api, method, path):
        response = api.client.request(method, path, json={} if method != "GET" else None)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfile:
    def test_get_own_profile(self, api):
        response = api.client.get("/api/v1/profile", headers=api.headers_a)
        assert response.status_code == 200
        assert response.json()["id"] == USER_A

    def test_patch_updates_only_permitted_fields(self, api):
        response = api.client.patch(
            "/api/v1/profile",
            headers=api.headers_a,
            json={"display_name": "New Name", "avatar_url": "https://x/y.png"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["display_name"] == "New Name"
        assert body["avatar_url"] == "https://x/y.png"

    def test_patch_ignores_mass_assignment_and_user_id(self, api):
        response = api.client.patch(
            "/api/v1/profile",
            headers=api.headers_a,
            json={"id": USER_B, "display_name": "ok", "is_admin": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == USER_A  # identity unchanged
        assert "is_admin" not in body

    def test_patch_rejects_oversized_display_name(self, api):
        response = api.client.patch(
            "/api/v1/profile",
            headers=api.headers_a,
            json={"display_name": "x" * 500},
        )
        assert response.status_code == 422

    def test_users_do_not_share_profiles(self, api):
        api.client.patch(
            "/api/v1/profile", headers=api.headers_a, json={"display_name": "A-only"}
        )
        body_b = api.client.get("/api/v1/profile", headers=api.headers_b).json()
        assert body_b["display_name"] != "A-only"


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


class TestFavorites:
    def test_create_and_list(self, api):
        created = api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        assert created.status_code == 201
        listed = api.client.get("/api/v1/favorites", headers=api.headers_a).json()
        assert len(listed) == 1
        assert listed[0]["provider_track_id"] == "tr-1"
        assert listed[0]["user_id"] == USER_A

    def test_duplicate_returns_existing_without_error(self, api):
        first = api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        second = api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert len(api.client.get("/api/v1/favorites", headers=api.headers_a).json()) == 1

    def test_delete_own_favorite(self, api):
        api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        deleted = api.client.delete(
            "/api/v1/favorites/jamendo/tr-1", headers=api.headers_a
        )
        assert deleted.status_code == 204
        assert api.client.get("/api/v1/favorites", headers=api.headers_a).json() == []

    def test_delete_unknown_favorite_is_404(self, api):
        response = api.client.delete(
            "/api/v1/favorites/jamendo/missing", headers=api.headers_a
        )
        assert response.status_code == 404

    def test_idor_delete_cannot_remove_other_users_favorite(self, api):
        api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        response = api.client.delete(
            "/api/v1/favorites/jamendo/tr-1", headers=api.headers_b
        )
        assert response.status_code == 404  # generic not-found, no existence leak
        assert len(api.client.get("/api/v1/favorites", headers=api.headers_a).json()) == 1

    def test_user_id_in_body_cannot_assign_another_user(self, api):
        payload = {**TRACK, "user_id": USER_B}
        created = api.client.post("/api/v1/favorites", json=payload, headers=api.headers_a)
        assert created.status_code in (200, 201)
        assert created.json()["user_id"] == USER_A

    def test_invalid_provider_rejected(self, api):
        response = api.client.post(
            "/api/v1/favorites", json={**TRACK, "provider": "spotify"}, headers=api.headers_a
        )
        assert response.status_code == 422

    def test_blank_artist_rejected(self, api):
        response = api.client.post(
            "/api/v1/favorites", json={**TRACK, "artist": ""}, headers=api.headers_a
        )
        assert response.status_code == 422

    def test_lists_are_scoped_per_user(self, api):
        api.client.post("/api/v1/favorites", json=TRACK, headers=api.headers_a)
        other = {**TRACK, "provider_track_id": "tr-2"}
        api.client.post("/api/v1/favorites", json=other, headers=api.headers_b)
        assert len(api.client.get("/api/v1/favorites", headers=api.headers_a).json()) == 1
        assert len(api.client.get("/api/v1/favorites", headers=api.headers_b).json()) == 1

        
    def test_list_supports_pagination(self, api):
        for i in range(3):
            api.client.post(
                "/api/v1/favorites", json={**TRACK, "provider_track_id": f"tr-{i}"},
                headers=api.headers_a,
            )
        assert len(api.client.get("/api/v1/favorites?limit=2&offset=0", headers=api.headers_a).json()) == 2
        assert len(api.client.get("/api/v1/favorites?limit=10&offset=1", headers=api.headers_a).json()) == 2
        assert len(api.client.get("/api/v1/favorites?limit=100&offset=0", headers=api.headers_a).json()) == 3
                # The documented cap is 100; a value beyond it is a 422, never an
        # unbounded page.
        assert api.client.get("/api/v1/favorites?limit=999&offset=0", headers=api.headers_a).status_code == 422



# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------


class TestPlaylists:
    def test_create_and_list_own(self, api):
        created = api.client.post(
            "/api/v1/playlists", json={"name": "My List"}, headers=api.headers_a
        )
        assert created.status_code == 201
        body = created.json()
        pl_id = body["id"]
        assert body["user_id"] == USER_A
        assert body["is_public"] is False
        listed = api.client.get("/api/v1/playlists", headers=api.headers_a).json()
        assert any(p["id"] == pl_id for p in listed)

    def test_get_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        response = api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_a)
        assert response.status_code == 200
        assert response.json()["name"] == "L"

    def test_update_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "Old"}, headers=api.headers_a
        ).json()["id"]
        response = api.client.patch(
            f"/api/v1/playlists/{pl_id}", json={"name": "New", "is_public": True},
            headers=api.headers_a,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New"
        assert response.json()["is_public"] is True
        assert response.json()["user_id"] == USER_A  # not client-changeable

    def test_update_rejects_user_id_in_body(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        resp = api.client.patch(
            f"/api/v1/playlists/{pl_id}",
            json={"name": "ok", "user_id": USER_B},
            headers=api.headers_a,
        )
        assert resp.status_code == 200
        assert resp.json()["user_id"] == USER_A

    def test_delete_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "D"}, headers=api.headers_a
        ).json()["id"]
        assert api.client.delete(f"/api/v1/playlists/{pl_id}", headers=api.headers_a).status_code == 204
        assert api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_a).status_code == 404

    def test_owner_reads_private(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "P", "is_public": False}, headers=api.headers_a
        ).json()["id"]
        assert api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_a).status_code == 200

    def test_non_owner_cannot_read_private(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "Private", "is_public": False}, headers=api.headers_a
        ).json()["id"]
        assert api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_b).status_code == 404

    def test_public_playlist_readable_by_non_owner(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "Pub", "is_public": True}, headers=api.headers_a
        ).json()["id"]
        assert api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_b).status_code == 200

    def test_non_owner_cannot_update_public_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "Pub", "is_public": True}, headers=api.headers_a
        ).json()["id"]
        resp = api.client.patch(f"/api/v1/playlists/{pl_id}", json={"name": "Hijack"}, headers=api.headers_b)
        assert resp.status_code == 404
        current = api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_a).json()
        assert current["name"] == "Pub"

    def test_non_owner_cannot_delete_public_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "Pub", "is_public": True}, headers=api.headers_a
        ).json()["id"]
        assert api.client.delete(f"/api/v1/playlists/{pl_id}", headers=api.headers_b).status_code == 404
        assert api.client.get(f"/api/v1/playlists/{pl_id}", headers=api.headers_a).status_code == 200

    def test_invalid_uuid_playlist_id(self, api):
        resp = api.client.get("/api/v1/playlists/not-a-uuid", headers=api.headers_a)
        assert resp.status_code == 422

    def test_create_rejects_missing_name(self, api):
        assert api.client.post(
            "/api/v1/playlists", json={}, headers=api.headers_a
        ).status_code == 422

    def test_create_rejects_oversized_name(self, api):
        assert api.client.post(
            "/api/v1/playlists", json={"name": "x" * 500}, headers=api.headers_a
        ).status_code == 422


# ---------------------------------------------------------------------------
# Playlist tracks
# ---------------------------------------------------------------------------


class TestPlaylistTracks:
    def test_add_track_to_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        resp = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a
        )
        assert resp.status_code == 201
        assert resp.json()["position"] == 0
        assert resp.json()["playlist_id"] == pl_id

    def test_list_tracks_for_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        api.client.post(f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a)
        tracks = api.client.get(
            f"/api/v1/playlists/{pl_id}/tracks", headers=api.headers_a
        ).json()
        assert len(tracks) == 1
        assert tracks[0]["provider_track_id"] == "tr-1"

    def test_reorder_track_on_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        t1 = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a
        ).json()
        api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks",
            json={**TRACK, "provider_track_id": "tr-2"},
            headers=api.headers_a,
        )
        resp = api.client.patch(
            f"/api/v1/playlists/{pl_id}/tracks/{t1['id']}", json={"position": 9},
            headers=api.headers_a,
        )
        assert resp.status_code == 200
        assert resp.json()["position"] == 9

    def test_delete_track_from_own_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        t1 = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a
        ).json()
        assert api.client.delete(
            f"/api/v1/playlists/{pl_id}/tracks/{t1['id']}", headers=api.headers_a
        ).status_code == 204
        assert api.client.get(
            f"/api/v1/playlists/{pl_id}/tracks", headers=api.headers_a
        ).json() == []

    def test_duplicate_track_in_playlist_is_409(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        api.client.post(f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a)
        resp = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a
        )
        assert resp.status_code == 409

    def test_non_owner_cannot_read_tracks(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L", "is_public": False}, headers=api.headers_a
        ).json()["id"]
        api.client.post(f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a)
        assert api.client.get(
            f"/api/v1/playlists/{pl_id}/tracks", headers=api.headers_b
        ).status_code == 404

    def test_non_owner_cannot_add_track(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L"}, headers=api.headers_a
        ).json()["id"]
        resp = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_b
        )
        assert resp.status_code == 404

    def test_non_owner_cannot_modify_tracks_on_public_playlist(self, api):
        pl_id = api.client.post(
            "/api/v1/playlists", json={"name": "L", "is_public": True}, headers=api.headers_a
        ).json()["id"]
        t1 = api.client.post(
            f"/api/v1/playlists/{pl_id}/tracks", json=TRACK, headers=api.headers_a
        ).json()
        resp = api.client.patch(
            f"/api/v1/playlists/{pl_id}/tracks/{t1['id']}", json={"position": 5},
            headers=api.headers_b,
        )
        assert resp.status_code == 404

    def test_invalid_playlist_uuid_422(self, api):
        resp = api.client.get("/api/v1/playlists/not-a-uuid/tracks", headers=api.headers_a)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Recently played / listening history
# ---------------------------------------------------------------------------


class TestRecentlyPlayed:
    def test_record_and_list_own_history(self, api):
        resp = api.client.post("/api/v1/recently-played", json=TRACK, headers=api.headers_a)
        assert resp.status_code == 201
        assert resp.json()["user_id"] == USER_A
        listed = api.client.get("/api/v1/recently-played", headers=api.headers_a).json()
        assert len(listed) == 1
        assert listed[0]["provider_track_id"] == "tr-1"

    def test_cannot_read_another_users_history(self, api):
        api.client.post("/api/v1/recently-played", json=TRACK, headers=api.headers_a)
        history = api.client.get("/api/v1/recently-played", headers=api.headers_b).json()
        assert len(history) == 0

    def test_user_id_in_body_cannot_assign_another_user(self, api):
        payload = {**TRACK, "user_id": USER_B}
        resp = api.client.post("/api/v1/recently-played", json=payload, headers=api.headers_a)
        assert resp.status_code == 201
        assert resp.json()["user_id"] == USER_A

    def test_invalid_provider_rejected(self, api):
        resp = api.client.post(
            "/api/v1/recently-played", json={**TRACK, "provider": "spotify"},
            headers=api.headers_a,
        )
        assert resp.status_code == 422

    def test_blank_artist_rejected(self, api):
        resp = api.client.post(
            "/api/v1/recently-played", json={**TRACK, "artist": ""},
            headers=api.headers_a,
        )
        assert resp.status_code == 422

    def test_recent_history_allows_duplicates(self, api):
        api.client.post("/api/v1/recently-played", json=TRACK, headers=api.headers_a)
        api.client.post("/api/v1/recently-played", json=TRACK, headers=api.headers_a)
        assert len(
            api.client.get("/api/v1/recently-played", headers=api.headers_a).json()
        ) == 2



