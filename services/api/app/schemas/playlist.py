"""Pydantic schemas for playlists and playlist tracks.

A playlist is owned by a :class:`~app.models.profile.Profile` and contains
ordered :class:`PlaylistTrack` entries.  ``position`` is the stable ordering
field; the ORM enforces uniqueness of ``(playlist_id, position)`` and prevents
the same provider track being added to a playlist twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ORMModel, TrackReferenceBase

#: Free-text playlist descriptions are bounded before they reach a TEXT column.
_MAX_DESCRIPTION_LENGTH = 2000


class PlaylistCreate(BaseModel):
    """Payload for creating a playlist.

    ``user_id`` is never accepted from the client — it is taken from the
    authenticated session.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200, description="Playlist name")
    description: Optional[str] = Field(
        default=None, max_length=_MAX_DESCRIPTION_LENGTH, description="Optional description"
    )
    is_public: bool = Field(default=False, description="Reserved for future sharing")


class PlaylistUpdate(BaseModel):
    """Editable playlist fields.  All fields are optional (partial update).

    Omitted fields are left untouched.  A field that is explicitly ``null``
    while its database column is ``NOT NULL`` (``name``, ``is_public``) is
    rejected with 422 — it must never reach the database, where it would fail
    a NOT NULL constraint and surface as an uncontrolled 500.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=_MAX_DESCRIPTION_LENGTH)
    is_public: Optional[bool] = Field(default=None)

    @model_validator(mode="after")
    def _reject_null_for_not_null_columns(self) -> "PlaylistUpdate":
        for field in ("name", "is_public"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} may not be null")
        return self


class PlaylistRead(ORMModel):
    """A stored playlist."""

    id: UUID
    user_id: UUID
    name: str
    description: Optional[str] = None
    is_public: bool
    created_at: datetime
    updated_at: datetime


class PlaylistTrackCreate(TrackReferenceBase):
    """Payload for adding a track to a playlist.

    ``position`` is optional: when omitted the track is appended to the end
    of the playlist.
    """

    position: Optional[int] = Field(
        default=None, ge=0, description="Zero-based ordering within the playlist"
    )


class PlaylistTrackRead(TrackReferenceBase):
    """A stored playlist entry, including its ordering position."""

    id: UUID
    playlist_id: UUID
    position: int
    added_at: datetime


__all__ = [
    "PlaylistCreate",
    "PlaylistUpdate",
    "PlaylistRead",
    "PlaylistTrackCreate",
    "PlaylistTrackRead",
]
