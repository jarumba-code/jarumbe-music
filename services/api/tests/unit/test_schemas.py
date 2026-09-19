"""Pydantic domain-schema tests.

The schemas are part of the API contract, so these tests pin down the rules
that matter to the database design: provider-based track references, no
client-supplied ownership, no credential fields, and bounded inputs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    FavoriteCreate,
    FavoriteRead,
    PlaylistCreate,
    PlaylistRead,
    PlaylistTrackCreate,
    PlaylistUpdate,
    ProfileRead,
    ProfileUpdate,
    RecentlyPlayedCreate,
    RecentlyPlayedRead,
    TrackReferenceBase,
)

#: A minimal valid provider-based track payload.
VALID_TRACK = {
    "provider": "jamendo",
    "provider_track_id": "2155141",
    "title": "Afrobeats Fusion",
    "artist": "Silver-Stage",
}


# ---------------------------------------------------------------------------
# TrackReferenceBase - the shared provider-reference contract
# ---------------------------------------------------------------------------

class TestTrackReferenceBase:
    def test_minimal_payload_is_valid(self):
        ref = TrackReferenceBase(**VALID_TRACK)
        assert ref.provider == "jamendo"
        assert ref.provider_track_id == "2155141"
        assert ref.album is None
        assert ref.duration is None
        assert ref.license_url is None

    @pytest.mark.parametrize("missing", ["provider", "provider_track_id", "title", "artist"])
    def test_provider_reference_fields_are_required(self, missing):
        payload = {k: v for k, v in VALID_TRACK.items() if k != missing}
        with pytest.raises(ValidationError):
            TrackReferenceBase(**payload)

    @pytest.mark.parametrize("field", ["provider", "provider_track_id", "title", "artist"])
    def test_blank_strings_are_rejected(self, field):
        with pytest.raises(ValidationError):
            TrackReferenceBase(**{**VALID_TRACK, field: ""})

    def test_duration_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            TrackReferenceBase(**VALID_TRACK, duration=-1)

    def test_license_information_is_preserved(self):
        ref = TrackReferenceBase(
            **VALID_TRACK,
            license_url="http://creativecommons.org/licenses/by-nc-nd/3.0/",
            license_name="CC BY-NC-ND",
        )
        assert ref.license_name == "CC BY-NC-ND"

    def test_no_audio_payload_fields(self):
        """Jarumba stores provider references, never audio blobs."""
        fields = set(TrackReferenceBase.model_fields)
        audio_like = {f for f in fields if "audio" in f or "stream" in f or "file" in f}
        assert not audio_like, f"unexpected audio fields: {audio_like}"


# ---------------------------------------------------------------------------
# Ownership must never come from the request body
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "schema_cls",
    [FavoriteCreate, PlaylistCreate, PlaylistTrackCreate, RecentlyPlayedCreate],
)
def test_create_schemas_do_not_accept_user_id(schema_cls):
    assert "user_id" not in schema_cls.model_fields


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------

class TestProfileSchemas:
    def test_profile_update_accepts_only_jarumba_fields(self):
        assert set(ProfileUpdate.model_fields) == {"display_name", "avatar_url"}

    @pytest.mark.parametrize(
        "forbidden",
        ["email", "password", "access_token", "refresh_token", "provider_token"],
    )
    def test_profile_update_never_models_credentials(self, forbidden):
        """Credential fields are not part of the schema and are not retained."""
        assert forbidden not in ProfileUpdate.model_fields
        payload = ProfileUpdate(**{forbidden: "value"})
        assert not hasattr(payload, forbidden)

    def test_display_name_bounded(self):
        with pytest.raises(ValidationError):
            ProfileUpdate(display_name="x" * 256)

    def test_profile_read_requires_id_and_timestamps(self):
        assert {"id", "created_at", "updated_at"} <= set(ProfileRead.model_fields)


# ---------------------------------------------------------------------------
# favorites
# ---------------------------------------------------------------------------

class TestFavoriteSchemas:
    def test_read_exposes_id_user_and_timestamp(self):
        assert {"id", "user_id", "created_at"} <= set(FavoriteRead.model_fields)


# ---------------------------------------------------------------------------
# playlists
# ---------------------------------------------------------------------------

class TestPlaylistSchemas:
    def test_create_does_not_accept_user_id(self):
        assert "user_id" not in PlaylistCreate.model_fields

    def test_name_is_required_and_non_blank(self):
        with pytest.raises(ValidationError):
            PlaylistCreate(name="")
        with pytest.raises(ValidationError):
            PlaylistCreate(name="x" * 201)

    def test_is_public_defaults_false(self):
        assert PlaylistCreate(name="Road trip").is_public is False

    def test_update_allows_partial_changes(self):
        assert PlaylistUpdate().model_dump(exclude_unset=True) == {}
        assert PlaylistUpdate(name="Renamed").name == "Renamed"

    def test_read_exposes_timestamps(self):
        assert {"created_at", "updated_at"} <= set(PlaylistRead.model_fields)

    def test_track_position_is_optional_and_non_negative(self):
        assert PlaylistTrackCreate(**VALID_TRACK).position is None
        with pytest.raises(ValidationError):
            PlaylistTrackCreate(**VALID_TRACK, position=-1)


# ---------------------------------------------------------------------------
# recently_played
# ---------------------------------------------------------------------------

class TestRecentlyPlayedSchemas:
    def test_create_does_not_accept_user_id(self):
        assert "user_id" not in RecentlyPlayedCreate.model_fields

    def test_read_exposes_played_at(self):
        assert "played_at" in RecentlyPlayedRead.model_fields