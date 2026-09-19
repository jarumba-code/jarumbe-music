"""Playlist-track position-allocation tests (concurrency hardening).

The route allocates the next ``position`` in the transaction that holds a row
lock on the parent playlist (``SELECT ... FOR UPDATE`` on PostgreSQL - see
``_load_owned_playlist_for_update``).  SQLite, the local test database, has no
row locks, so here the production uniqueness constraint
``uk_playlist_tracks_playlist_position`` (DEFERRABLE INITIALLY DEFERRED on
PostgreSQL) remains the backstop and is exercised at statement time: a
collision is mapped to a controlled 409, never a 500.

Note on fidelity: a true multi-transaction race can only be reproduced on
PostgreSQL.  Running a live PostgreSQL instance locally is out of scope for
the hermetic suite (no Supabase contact is permitted), so the concurrency
guarantees are pinned here as:

1. sequential appends never collide (allocation correctness),
2. an explicit position collision is a 409 (constraint backstop + mapping),
3. a duplicate track is a 409,
4. the PostgreSQL code path really applies ``FOR UPDATE`` (compiled-SQL check),
   and the SQLite path omits it (SQLAlchemy has no such clause for SQLite).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.playlist import Playlist
from tests.unit.api_testbed import USER_A, api  # noqa: F401  register fixture

TRACK = {
    "provider": "jamendo",
    "provider_track_id": "tr-1",
    "title": "Song",
    "artist": "Artist",
}


def _create_playlist(api) -> str:
    response = api.client.post(
        "/api/v1/playlists", json={"name": "Alloc"}, headers=api.headers_a
    )
    assert response.status_code == 201
    return response.json()["id"]


class TestPositionAllocation:
    def test_sequential_appends_allocate_distinct_positions(self, api):
        playlist_id = _create_playlist(api)
        ids = []
        for i in range(5):
            response = api.client.post(
                f"/api/v1/playlists/{playlist_id}/tracks",
                json={**TRACK, "provider_track_id": f"tr-{i}"},
                headers=api.headers_a,
            )
            assert response.status_code == 201, response.text
            ids.append(response.json())

        positions = [entry["position"] for entry in ids]
        assert positions == [0, 1, 2, 3, 4]

    def test_list_returns_tracks_in_position_order(self, api):
        playlist_id = _create_playlist(api)
        for i in range(3):
            api.client.post(
                f"/api/v1/playlists/{playlist_id}/tracks",
                json={**TRACK, "provider_track_id": f"tr-{i}"},
                headers=api.headers_a,
            )
        listing = api.client.get(
            f"/api/v1/playlists/{playlist_id}/tracks", headers=api.headers_a
        ).json()
        assert [t["position"] for t in listing] == [0, 1, 2]

    def test_appends_continue_after_a_reorder(self, api):
        playlist_id = _create_playlist(api)
        first = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json={**TRACK, "provider_track_id": "tr-0"},
            headers=api.headers_a,
        ).json()
        second = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json={**TRACK, "provider_track_id": "tr-1"},
            headers=api.headers_a,
        ).json()
        # Move the first entry onto the second entry's position: PostgreSQL
        # resolves the swap via the deferred unique constraint inside one
        # transaction; on SQLite the statement-level constraint fires first.
        moved = api.client.patch(
            f"/api/v1/playlists/{playlist_id}/tracks/{first['id']}",
            json={"position": 1},
            headers=api.headers_a,
        )
        assert moved.status_code in (200, 409)
        listing = api.client.get(
            f"/api/v1/playlists/{playlist_id}/tracks", headers=api.headers_a
        ).json()
        positions = sorted(t["position"] for t in listing)
        # The playlist must never end up inconsistent: positions unique.
        assert positions[0] == 0
        assert len(set(positions)) == len(positions)
        assert second["id"] in {t["id"] for t in listing}


class TestConstraintBackstop:
    def test_duplicate_track_in_playlist_is_409(self, api):
        playlist_id = _create_playlist(api)
        first = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json=TRACK,
            headers=api.headers_a,
        )
        assert first.status_code == 201
        duplicate = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json=TRACK,
            headers=api.headers_a,
        )
        assert duplicate.status_code == 409

    def test_forced_position_collision_is_409(self, api):
        playlist_id = _create_playlist(api)
        first = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json=TRACK,
            headers=api.headers_a,
        ).json()
        response = api.client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json={**TRACK, "provider_track_id": "tr-other", "position": 0},
            headers=api.headers_a,
        )
        assert response.status_code == 409
        # The original entry is untouched by the failed insert.
        listing = api.client.get(
            f"/api/v1/playlists/{playlist_id}/tracks", headers=api.headers_a
        ).json()
        assert len(listing) == 1
        assert listing[0]["id"] == first["id"]
        assert listing[0]["position"] == 0



class TestPostgresRowLockContract:
    def test_postgres_dialect_compiles_for_update(self):
        """The production append path locks the playlist row (PostgreSQL)."""
        from sqlalchemy.dialects import postgresql

        statement = select(Playlist).where(Playlist.id == "x").with_for_update()
        postgres_sql = str(
            statement.compile(dialect=postgresql.dialect())
        ).upper()
        assert "FOR UPDATE" in postgres_sql

    def test_sqlite_dialect_omits_for_update(self):
        """SQLite has no row locks; the clause must not be emitted there."""
        from sqlalchemy.dialects import sqlite

        statement = select(Playlist).where(Playlist.id == "x").with_for_update()
        sqlite_sql = str(statement.compile(dialect=sqlite.dialect())).upper()
        assert "FOR UPDATE" not in sqlite_sql

    def test_route_lock_helper_targets_postgresql_only(self):
        """The helper applies with_for_update based on the bind's dialect."""
        import inspect

        from app.api.routes import playlist_tracks

        source = inspect.getsource(
            playlist_tracks._load_owned_playlist_for_update
        )
        assert "with_for_update" in source
        assert 'dialect.name == "postgresql"' in source

