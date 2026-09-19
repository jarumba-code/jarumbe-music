"""Database model tests.

These tests are hermetic: they inspect SQLAlchemy metadata and compile DDL
with the PostgreSQL dialect, so they need **no** live database.  They verify
the schema *design* — keys, foreign keys, constraints, indexes, cascade rules
and ORM relationships — which is exactly what the migration step will
materialise onto Supabase PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.schema import CreateIndex, CreateTable

import pytest

from app.models import (
    DOMAIN_TABLES,
    Base,
    Favorite,
    Playlist,
    PlaylistTrack,
    Profile,
    RecentlyPlayed,
    auth_users,
)

PG = postgresql.dialect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_ddl(table) -> str:
    """Render the CREATE TABLE / CREATE INDEX statements for *table*."""
    statements = [str(CreateTable(table).compile(dialect=PG))]
    statements += [str(CreateIndex(idx).compile(dialect=PG)) for idx in table.indexes]
    return "\n".join(statements)


def unique_constraints(table) -> dict[str, UniqueConstraint]:
    return {
        c.name: c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name is not None
    }


def check_constraints(table) -> dict[str, CheckConstraint]:
    return {
        c.name: c
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def index_names(table) -> set[str]:
    return {idx.name for idx in table.indexes}


def fk_targets(table) -> dict[str, str]:
    """Map local column name -> ``schema.table.column`` for every FK."""
    return {fk.parent.name: fk.target_fullname for fk in table.foreign_keys}


def fk_ondelete(table) -> dict[str, str | None]:
    return {fk.parent.name: fk.ondelete for fk in table.foreign_keys}


def assert_timestamp_column(table, name: str) -> None:
    """Assert *name* is a NOT NULL timezone-aware timestamp with now() default."""
    column = table.c[name]
    assert isinstance(column.type, DateTime), f"{name} must be a DateTime"
    assert column.type.timezone is True, f"{name} must be timezone-aware"
    assert column.nullable is False, f"{name} must be NOT NULL"
    assert "now()" in table_ddl(table), f"{name} must default to now()"


# ---------------------------------------------------------------------------
# Metadata registration
# ---------------------------------------------------------------------------

class TestMetadataRegistration:
    def test_all_domain_tables_registered(self):
        names = {t.name for t in DOMAIN_TABLES}
        assert names == {
            "profiles",
            "favorites",
            "playlists",
            "playlist_tracks",
            "recently_played",
        }

    def test_domain_tables_exclude_supabase_auth(self):
        """Jarumba must never own/migrate the Supabase auth schema."""
        schemas = {t.schema for t in DOMAIN_TABLES}
        assert schemas == {None}
        assert "auth.users" not in {f"{t.schema}.{t.name}" for t in DOMAIN_TABLES}

    def test_auth_stub_is_marked_external(self):
        assert auth_users.schema == "auth"
        assert auth_users.name == "users"
        assert auth_users.info.get("external") is True
        # Only the primary key is modelled; Supabase owns the real table.
        assert list(auth_users.c.keys()) == ["id"]

    def test_models_share_one_declarative_base(self):
        for model in (Profile, Favorite, Playlist, PlaylistTrack, RecentlyPlayed):
            assert set(model.__bases__) == {Base}, "all models must share one Base"


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------

class TestProfilesTable:
    def test_table_name(self):
        assert Profile.__tablename__ == "profiles"

    def test_primary_key_is_a_uuid(self):
        id_col = Profile.__table__.c.id
        assert id_col.primary_key is True
        assert isinstance(id_col.type, PG_UUID)
        assert id_col.type.as_uuid is False

    def test_id_foreign_key_points_at_supabase_auth_users(self):
        assert fk_targets(Profile.__table__) == {"id": "auth.users.id"}

    def test_deleting_supabase_user_cascades_to_profile(self):
        assert fk_ondelete(Profile.__table__) == {"id": "CASCADE"}

    def test_no_authentication_columns_are_stored(self):
        """profiles holds only Jarumba data - never credentials."""
        columns = set(Profile.__table__.c.keys())
        forbidden = {
            "email",
            "password",
            "password_hash",
            "hashed_password",
            "encrypted_password",
            "access_token",
            "refresh_token",
            "provider_token",
            "oauth_token",
            "salt",
        }
        leaked = columns & forbidden
        assert not leaked, f"credential columns must not exist: {leaked}"

    def test_expected_columns(self):
        assert set(Profile.__table__.c.keys()) == {
            "id",
            "display_name",
            "avatar_url",
            "created_at",
            "updated_at",
        }

    def test_display_name_optional_but_bounded(self):
        col = Profile.__table__.c.display_name
        assert col.nullable is True
        assert col.type.length == 255

    def test_timestamps_are_timezone_aware(self):
        assert_timestamp_column(Profile.__table__, "created_at")
        assert_timestamp_column(Profile.__table__, "updated_at")

    def test_display_name_index(self):
        assert "idx_profiles_display_name" in index_names(Profile.__table__)


# ---------------------------------------------------------------------------
# favorites
# ---------------------------------------------------------------------------

class TestFavoritesTable:
    def test_table_name(self):
        assert Favorite.__tablename__ == "favorites"

    def test_uuid_primary_key_with_server_default(self):
        assert "id UUID DEFAULT gen_random_uuid() NOT NULL" in table_ddl(
            Favorite.__table__
        )

    def test_owner_foreign_key_cascades(self):
        table = Favorite.__table__
        assert fk_targets(table) == {"user_id": "profiles.id"}
        assert fk_ondelete(table) == {"user_id": "CASCADE"}

    def test_duplicate_favorite_is_prevented(self):
        uniques = unique_constraints(Favorite.__table__)
        assert "uk_favorites_user_provider_track" in uniques
        cols = {c.name for c in uniques["uk_favorites_user_provider_track"].columns}
        assert cols == {"user_id", "provider", "provider_track_id"}

    def test_user_created_at_index(self):
        assert "idx_favorites_user_created_at" in index_names(Favorite.__table__)

    def test_stores_provider_reference_not_audio(self):
        columns = set(Favorite.__table__.c.keys())
        assert {"provider", "provider_track_id"} <= columns
        audio_like = {c for c in columns if "audio" in c or "stream" in c or "file" in c}
        assert not audio_like, f"favorites must not store audio: {audio_like}"

    def test_metadata_snapshot_columns(self):
        assert {"title", "artist", "album", "duration", "artwork_url"} <= set(
            Favorite.__table__.c.keys()
        )

    def test_license_information_preserved(self):
        assert {"license_url", "license_name"} <= set(Favorite.__table__.c.keys())

    def test_title_and_artist_are_required(self):
        assert Favorite.__table__.c.title.nullable is False
        assert Favorite.__table__.c.artist.nullable is False

    def test_created_at(self):
        assert_timestamp_column(Favorite.__table__, "created_at")


# ---------------------------------------------------------------------------
# playlists
# ---------------------------------------------------------------------------

class TestPlaylistsTable:
    def test_table_name(self):
        assert Playlist.__tablename__ == "playlists"

    def test_owner_foreign_key_cascades(self):
        table = Playlist.__table__
        assert fk_targets(table) == {"user_id": "profiles.id"}
        assert fk_ondelete(table) == {"user_id": "CASCADE"}

    def test_timestamps(self):
        assert_timestamp_column(Playlist.__table__, "created_at")
        assert_timestamp_column(Playlist.__table__, "updated_at")

    def test_name_is_required_and_bounded(self):
        col = Playlist.__table__.c.name
        assert col.nullable is False
        assert col.type.length == 200

    def test_is_public_defaults_to_false(self):
        assert "is_public BOOLEAN DEFAULT false NOT NULL" in table_ddl(
            Playlist.__table__
        )

    def test_user_created_at_index(self):
        assert "idx_playlists_user_created_at" in index_names(Playlist.__table__)


# ---------------------------------------------------------------------------
# playlist_tracks
# ---------------------------------------------------------------------------

class TestPlaylistTracksTable:
    def test_table_name(self):
        assert PlaylistTrack.__tablename__ == "playlist_tracks"

    def test_playlist_foreign_key_cascades(self):
        table = PlaylistTrack.__table__
        assert fk_targets(table) == {"playlist_id": "playlists.id"}
        assert fk_ondelete(table) == {"playlist_id": "CASCADE"}

    def test_position_is_required(self):
        col = PlaylistTrack.__table__.c.position
        assert col.nullable is False
        assert col.type.python_type is int

    def test_position_is_unique_per_playlist(self):
        uniques = unique_constraints(PlaylistTrack.__table__)
        assert "uk_playlist_tracks_playlist_position" in uniques
        cols = {c.name for c in uniques["uk_playlist_tracks_playlist_position"].columns}
        assert cols == {"playlist_id", "position"}

    def test_position_constraint_is_deferrable(self):
        """A reorder must shuffle positions inside one transaction."""
        constraint = unique_constraints(PlaylistTrack.__table__)[
            "uk_playlist_tracks_playlist_position"
        ]
        assert constraint.deferrable is True
        assert constraint.initially == "DEFERRED"
        assert "DEFERRABLE INITIALLY DEFERRED" in table_ddl(PlaylistTrack.__table__)

    def test_position_must_be_non_negative(self):
        checks = check_constraints(PlaylistTrack.__table__)
        assert "ck_playlist_tracks_position_non_negative" in checks

    def test_duplicate_track_in_same_playlist_is_prevented(self):
        uniques = unique_constraints(PlaylistTrack.__table__)
        assert "uk_playlist_tracks_playlist_track" in uniques
        cols = {c.name for c in uniques["uk_playlist_tracks_playlist_track"].columns}
        assert cols == {"playlist_id", "provider", "provider_track_id"}

    def test_no_audio_payload_columns(self):
        columns = set(PlaylistTrack.__table__.c.keys())
        audio_like = {c for c in columns if "audio" in c or "stream" in c or "file" in c}
        assert not audio_like

    def test_snapshot_and_license_columns(self):
        columns = set(PlaylistTrack.__table__.c.keys())
        assert {"title", "artist", "album", "duration", "artwork_url"} <= columns
        assert {"license_url", "license_name"} <= columns

    def test_added_at_timestamp(self):
        assert_timestamp_column(PlaylistTrack.__table__, "added_at")


# ---------------------------------------------------------------------------
# recently_played
# ---------------------------------------------------------------------------

class TestRecentlyPlayedTable:
    def test_table_name(self):
        assert RecentlyPlayed.__tablename__ == "recently_played"

    def test_owner_foreign_key_cascades(self):
        table = RecentlyPlayed.__table__
        assert fk_targets(table) == {"user_id": "profiles.id"}
        assert fk_ondelete(table) == {"user_id": "CASCADE"}

    def test_repeated_plays_are_allowed(self):
        """Play history is temporal - no unique constraint on the track."""
        uniques = unique_constraints(RecentlyPlayed.__table__)
        assert uniques == {}, f"history must not deduplicate: {list(uniques)}"

    def test_history_indexes(self):
        names = index_names(RecentlyPlayed.__table__)
        assert "idx_recently_played_user_played_at" in names
        assert "idx_recently_played_user_provider_track" in names

    def test_played_at_timestamp(self):
        assert_timestamp_column(RecentlyPlayed.__table__, "played_at")

    def test_provider_reference_columns(self):
        assert {"provider", "provider_track_id"} <= set(
            RecentlyPlayed.__table__.c.keys()
        )


# ---------------------------------------------------------------------------
# ORM relationships
# ---------------------------------------------------------------------------

class TestRelationships:
    def test_profile_owns_favorites_playlists_and_history(self):
        rels = Profile.__mapper__.relationships
        assert {"favorites", "playlists", "recently_played"} <= set(rels.keys())
        assert rels["favorites"].mapper.class_ is Favorite
        assert rels["playlists"].mapper.class_ is Playlist
        assert rels["recently_played"].mapper.class_ is RecentlyPlayed

    @pytest.mark.parametrize("name", ["favorites", "playlists", "recently_played"])
    def test_profile_owned_collections_delete_orphans(self, name):
        rel = Profile.__mapper__.relationships[name]
        assert "delete-orphan" in rel.cascade
        assert rel.passive_deletes is True

    def test_playlist_tracks_delete_orphans(self):
        rel = Playlist.__mapper__.relationships["tracks"]
        assert rel.mapper.class_ is PlaylistTrack
        assert "delete-orphan" in rel.cascade
        assert rel.passive_deletes is True

    def test_playlist_tracks_are_ordered_by_position(self):
        """Ordering must be deterministic, not insertion-order dependent."""
        rel = Playlist.__mapper__.relationships["tracks"]
        assert rel.order_by is not None
        # ``order_by`` resolves to the actual Column when inspected.
        assert "position" in str(rel.order_by)

    def test_back_populates_is_symmetric(self):
        pairs = [
            (Profile, "favorites", Favorite, "profile"),
            (Profile, "playlists", Playlist, "owner"),
            (Profile, "recently_played", RecentlyPlayed, "profile"),
            (Playlist, "tracks", PlaylistTrack, "playlist"),
        ]
        for parent, parent_attr, child, child_attr in pairs:
            forward = parent.__mapper__.relationships[parent_attr]
            assert forward.back_populates == child_attr
            reverse = child.__mapper__.relationships[child_attr]
            assert reverse.back_populates == parent_attr

    def test_owner_relationship_does_not_cascade_delete(self):
        """Deleting a playlist must not delete its owner profile."""
        rel = Playlist.__mapper__.relationships["owner"]
        assert "delete" not in rel.cascade


