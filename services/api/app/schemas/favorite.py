"""Pydantic schemas for favorites (liked / saved tracks)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import TrackReferenceBase


class FavoriteCreate(TrackReferenceBase):
    """Payload for favouriting a track.

    ``user_id`` is never accepted from the client — it is taken from the
    authenticated session.  The database unique constraint on
    ``(user_id, provider, provider_track_id)`` prevents duplicates.
    """


class FavoriteRead(TrackReferenceBase):
    """A stored favourite."""

    id: UUID
    user_id: UUID
    created_at: datetime


__all__ = ["FavoriteCreate", "FavoriteRead"]