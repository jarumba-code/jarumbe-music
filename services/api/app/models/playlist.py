"""Playlist model — a user-curated, ordered collection of tracks."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.playlist_track import PlaylistTrack
    from app.models.profile import Profile


class Playlist(Base):
    """A playlist owned by a single profile.

    Deleting the owner profile cascades to the playlist, and deleting a
    playlist cascades to its :class:`~app.models.playlist_track.PlaylistTrack`
    rows.
    """

    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Playlist primary key",
    )
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owning profile (profiles.id)",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="User-visible playlist name",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional free-text description",
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="Reserved for future sharing support",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=utcnow,
        onupdate=utcnow,
    )

    # -- relationships ---------------------------------------------------
    owner: Mapped["Profile"] = relationship(back_populates="playlists")
    tracks: Mapped[list["PlaylistTrack"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PlaylistTrack.position",
    )

    __table_args__ = (
        # Listing a user's playlists, newest first.
        Index("idx_playlists_user_created_at", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Playlist id={self.id} name={self.name!r}>"