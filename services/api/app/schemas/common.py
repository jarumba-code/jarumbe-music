"""Shared Pydantic building blocks for Jarumba domain schemas.

Jarumba stores music as **provider references** (``provider`` +
``provider_track_id``) plus a metadata snapshot.  It never stores audio
files in PostgreSQL.  :class:`TrackReferenceBase` captures that shared shape
so favorites, playlist tracks, and listening-history entries all validate
their track payloads identically.

Provider validation is server-side: ``provider`` is the allow-list enum from
:mod:`app.providers.registry`, so favorites, playlist tracks and
recently-played enforce exactly the same contract and a future provider only
has to be registered once.

Client-supplied ``license_url`` / ``license_name`` are **display metadata
only** — snapshot values stored for rendering.  They are never treated as
authoritative licensing evidence; the provider's own normalised response is
the source of truth.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.providers.registry import (
    MusicProvider,
    UnsupportedProviderError,
    validate_provider,
)

#: URL fields are bounded and restricted to http(s) absolute URLs.
_MAX_URL_LENGTH = 2048
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _validate_optional_http_url(value: object, field_name: str) -> object:
    """Accept ``None`` / empty, or an absolute http(s) URL of bounded length.

    Rejects relative paths, other schemes (``javascript:``, ``file:``, ``data:``)
    and over-long values so a client cannot store a hostile URL or smuggle an
    oversized payload into a text column.
    """
    if value is None or not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate:
        return None
    if len(candidate) > _MAX_URL_LENGTH:
        raise ValueError(f"{field_name} must be at most {_MAX_URL_LENGTH} characters")
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in _ALLOWED_URL_SCHEMES or not parts.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL")
    return candidate


class ORMModel(BaseModel):
    """Base class for schemas populated from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class TrackReferenceBase(BaseModel):
    """Provider-based music reference shared across domain schemas.

    ``provider`` and ``provider_track_id`` identify the track at the music
    provider.  The remaining fields are a snapshot of the metadata needed to
    render the track without another provider round-trip.

    License information is carried through so later business rules can decide
    whether a track may be streamed, cached, or downloaded.
    """

    model_config = ConfigDict(
        from_attributes=True,
        # Enum values are stored as plain strings, so payloads keep the exact
        # JSON shape (``"jamendo"``) the database columns and API contract use.
        use_enum_values=True,
        # "   " must never satisfy a min_length=1 bound.
        str_strip_whitespace=True,
    )

    # Server-side allow-list: only providers actually implemented by this API
    # (see app.providers.registry).  Unknown values are a 422 validation error,
    # never a silently stored row.
    provider: MusicProvider = Field(
        ..., description="Supported music provider (allow-list)",
    )
    provider_track_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Track identifier at the provider",
    )
    title: str = Field(..., min_length=1, max_length=500, description="Track title")
    artist: str = Field(..., min_length=1, max_length=500, description="Artist name")
    album: Optional[str] = Field(default=None, max_length=500, description="Album name")
    duration: Optional[int] = Field(
        default=None, ge=0, description="Duration in seconds"
    )
    artwork_url: Optional[str] = Field(
        default=None, description="Album art / cover image URL"
    )
    license_url: Optional[str] = Field(
        default=None, description="URL of the content license"
    )
    license_name: Optional[str] = Field(
        default=None, max_length=100, description="Short license identifier"
    )

    @field_validator("provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value: object) -> object:
        """Trim/lower-case the provider and reject unsupported ones."""
        if isinstance(value, str):
            try:
                return validate_provider(value)
            except UnsupportedProviderError as exc:
                raise ValueError(str(exc)) from exc
        return value

    @field_validator("artwork_url", "license_url", mode="before")
    @classmethod
    def _validate_urls(cls, value: object, info: ValidationInfo) -> object:
        return _validate_optional_http_url(value, str(info.field_name))


class TimestampedRead(ORMModel):
    """Mixin for read schemas that expose a creation timestamp."""

    created_at: datetime = Field(..., description="Row creation timestamp (UTC)")


__all__ = ["ORMModel", "TrackReferenceBase", "TimestampedRead"]