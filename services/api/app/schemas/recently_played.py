"""Pydantic schemas for listening history.

History is temporal: the same track may appear many times, each with its own
``played_at``.  There is deliberately no uniqueness constraint on the track
reference at the database level.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import TrackReferenceBase


class RecentlyPlayedCreate(TrackReferenceBase):
    """Payload for recording a play event.

    ``user_id`` is taken from the authenticated session, never from the body.
    """


class RecentlyPlayedRead(TrackReferenceBase):
    """A stored play event."""

    id: UUID
    user_id: UUID
    played_at: datetime


__all__ = ["RecentlyPlayedCreate", "RecentlyPlayedRead"]