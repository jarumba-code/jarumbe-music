"""Pydantic schemas for the public API contract."""

from app.schemas.auth import AuthMeResponse
from app.schemas.common import ORMModel, TimestampedRead, TrackReferenceBase
from app.schemas.favorite import FavoriteCreate, FavoriteRead
from app.schemas.music import SearchResponse, TrackResponse
from app.schemas.playlist import (
    PlaylistCreate,
    PlaylistRead,
    PlaylistTrackCreate,
    PlaylistTrackRead,
    PlaylistUpdate,
)
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.schemas.recently_played import RecentlyPlayedCreate, RecentlyPlayedRead

__all__ = [
    # shared building blocks
    "ORMModel",
    "TrackReferenceBase",
    "TimestampedRead",
    # music search (Jamendo-backed)
    "TrackResponse",
    "SearchResponse",
    # auth
    "AuthMeResponse",
    # profiles
    "ProfileRead",
    "ProfileUpdate",
    # favorites
    "FavoriteCreate",
    "FavoriteRead",
    # playlists
    "PlaylistCreate",
    "PlaylistUpdate",
    "PlaylistRead",
    "PlaylistTrackCreate",
    "PlaylistTrackRead",
    # listening history
    "RecentlyPlayedCreate",
    "RecentlyPlayedRead",
]

