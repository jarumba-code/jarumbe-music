"""Pydantic schemas for playlist track mutations (create, read, reorder)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import TrackReferenceBase


class PlaylistTrackCreate(TrackReferenceBase):
    """Payload for adding a provider track to a playlist.

    ``position`` is optional: when omitted the track is appended after the
    last existing entry (computed server-side).  A client-supplied position
    must be non-negative and must not collide with an existing entry.
    """

    position: Optional[int] = Field(
        default=None,
        ge=0,
        description="Zero-based ordering; omit to append at the end",
    )


class PlaylistTrackUpdate(BaseModel):
    """Editable playlist-entry fields.

    Only ``position`` is mutable: the metadata snapshot is immutable through
    the API (a playlist entry references a specific provider track; fixing a
    wrong title means removing and re-adding the track).
    """

    position: int = Field(..., ge=0, description="Zero-based ordering within the playlist")


class PlaylistTrackRead(TrackReferenceBase):
    """A stored playlist entry."""

    id: UUID
    playlist_id: UUID
    position: int
    added_at: datetime


__all__ = ["PlaylistTrackCreate", "PlaylistTrackUpdate", "PlaylistTrackRead"]
