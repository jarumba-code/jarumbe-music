"""Provider abstraction layer.

Defines the :class:`Track` dataclass — the normalised, provider-agnostic
representation that every music provider must produce — and the
:class:`BaseProvider` abstract base class.

Keeping this layer separate from the HTTP route layer means the API contract
(``app.schemas``) and business logic never depend on Jamendo's response shape
directly.  Adding a new provider (e.g. Audiomack) later is a matter of
implementing :class:`BaseProvider`; no routes or schemas need to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field


class ProviderError(Exception):
    """Base exception for all provider-related errors."""


class ProviderUnavailableError(ProviderError):
    """The provider is unavailable (network error, timeout, HTTP error)."""


class ProviderResponseError(ProviderError):
    """The provider returned an invalid or unexpected response."""


class Track(BaseModel):
    """
    Normalised, provider-agnostic track representation.

    Every provider implementation must map its raw response into this model.
    The rest of Jarumba works exclusively with this shape — raw provider
    payloads are never exposed on the public API.
    """

    provider: str = Field(..., description="Provider name, e.g. 'jamendo'")
    provider_track_id: str = Field(..., description="Track ID from the provider")
    title: str = Field(..., description="Track title")
    artist: str = Field(..., description="Artist or band name")
    album: Optional[str] = Field(default=None, description="Album name")
    duration: Optional[int] = Field(default=None, description="Duration in seconds")
    artwork_url: Optional[str] = Field(default=None, description="Album art / cover image URL")
    stream_url: Optional[str] = Field(default=None, description="Streaming audio URL")
    download_url: Optional[str] = Field(default=None, description="Direct download URL")
    download_allowed: bool = Field(default=False, description="Whether the track may be downloaded")
    license_url: Optional[str] = Field(default=None, description="URL of the content license")
    license_name: Optional[str] = Field(default=None, description="Short license identifier, e.g. 'CC BY-SA'")
    source_url: Optional[str] = Field(default=None, description="Provider source page URL")
    release_date: Optional[str] = Field(default=None, description="Release date (ISO 8601 if available)")

    model_config = {"extra": "ignore"}


class BaseProvider(ABC):
    """Abstract base class that every music provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'jamendo')."""

    @abstractmethod
    async def search_tracks(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Track]:
        """Search for tracks matching *query*.

        Returns a list of normalised :class:`Track` objects.
        """

    @abstractmethod
    async def get_track(self, provider_track_id: str) -> Optional[Track]:
        """Retrieve a single track by its provider-specific ID.

        Returns ``None`` when the track is not found.
        """

    @staticmethod
    @abstractmethod
    def normalize(raw: dict) -> Track:
        """Map a raw provider response dict to a :class:`Track`."""
