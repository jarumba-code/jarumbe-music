"""PlaylistTrack model — a provider track positioned inside a playlist.

Jarumba never stores audio in PostgreSQL.  A playlist entry is a
*provider reference* (``provider`` + ``provider_track_id``) plus a metadata
snapshot so the playlist still renders if the provider changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.playlist import Playlist


class PlaylistTrack(Base):
    """One ordered entry in a :class:`~app.models.playlist.Playlist`.

    Duplicate prevention
    --------------------
    ``uk_playlist_tracks_playlist_track`` stops the same provider track from
    being added to the same playlist twice.

    Stable ordering
    ---------------
    ``position`` is a non-null, non-negative integer.  The
    ``uk_playlist_tracks_playlist_position`` unique constraint is
    ``DEFERRABLE INITIALLY DEFERRED`` so a reorder can shuffle positions
    inside a single transaction without tripping the constraint mid-update,
    while still guaranteeing a deterministic (tie-free) ordering.
    """

    __tablename__ = "playlist_tracks"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    playlist_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("playlists.id", ondelete="CASCADE"),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Zero-based ordering within the playlist",
    )

    # -- provider reference ----------------------------------------------
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # -- metadata snapshot -----------------------------------------------
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artwork_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    license_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=utcnow,
    )

    # -- relationships ---------------------------------------------------
    playlist: Mapped["Playlist"] = relationship(back_populates="tracks")

    __table_args__ = (
        UniqueConstraint(
            "playlist_id",
            "position",
            name="uk_playlist_tracks_playlist_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "playlist_id",
            "provider",
            "provider_track_id",
            name="uk_playlist_tracks_playlist_track",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_playlist_tracks_position_non_negative",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<PlaylistTrack playlist_id={self.playlist_id} "
            f"position={self.position} provider={self.provider}:{self.provider_track_id}>"
        )