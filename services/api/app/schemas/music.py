"""Public API schemas for music endpoints.

These Pydantic models define the JSON contract that the frontend (and any
other consumer) will actually see.  They are deliberately decoupled from the
internal :class:`~app.providers.base.Track` so that provider response shapes
can change without breaking the public API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.providers.base import Track


class TrackResponse(BaseModel):
    """Normalised track representation returned by the public API."""

    provider: str = Field(..., description="Music provider name (e.g. 'jamendo')")
    provider_track_id: str = Field(..., description="Track identifier from the provider")
    title: str = Field(..., description="Track title")
    artist: str = Field(..., description="Artist or band name")
    album: Optional[str] = Field(default=None, description="Album name")
    duration: Optional[int] = Field(
        default=None,
        description="Track duration in seconds",
        ge=0,
    )
    artwork_url: Optional[str] = Field(default=None, description="Album art / cover image URL")
    stream_url: Optional[str] = Field(default=None, description="Streaming audio URL")
    download_url: Optional[str] = Field(default=None, description="Direct download URL")
    download_allowed: bool = Field(default=False, description="Whether the track may be downloaded")
    license_url: Optional[str] = Field(default=None, description="URL of the content license")
    license_name: Optional[str] = Field(default=None, description="Short license identifier (e.g. 'CC BY-SA')")
    source_url: Optional[str] = Field(default=None, description="Provider source page URL")
    release_date: Optional[str] = Field(default=None, description="Release date (ISO 8601 if available)")

    @classmethod
    def from_track(cls, track: Track) -> "TrackResponse":
        """Build a :class:`TrackResponse` from an internal :class:`Track`."""
        return cls(
            provider=track.provider,
            provider_track_id=track.provider_track_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration=track.duration,
            artwork_url=track.artwork_url,
            stream_url=track.stream_url,
            download_url=track.download_url,
            download_allowed=track.download_allowed,
            license_url=track.license_url,
            license_name=track.license_name,
            source_url=track.source_url,
            release_date=track.release_date,
        )


class SearchResponse(BaseModel):
    """Response body for :meth:`Jarumba.api.routes.music.search_music`."""

    query: str = Field(..., description="The normalised search query")
    limit: int = Field(..., description="Maximum results requested")
    offset: int = Field(..., description="Offset into the result set")
    total: int = Field(..., description="Number of results returned")
    results: list[TrackResponse] = Field(default_factory=list, description="Matching tracks")
