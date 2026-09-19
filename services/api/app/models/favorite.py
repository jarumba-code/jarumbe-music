"""Favorite model — tracks a user has liked/saved."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
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
    from app.models.profile import Profile


class Favorite(Base):
    """A track that a user has favorited / liked.

    The same user cannot favorite the same provider track twice (enforced
    by a unique constraint on ``(user_id, provider, provider_track_id)``).

    Metadata fields (title, artist, …) are **snapshotted** so the favorite
    remains meaningful even if the provider later changes or removes the
    track.
    """

    __tablename__ = "favorites"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(255), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artwork_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    license_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=utcnow,
    )

    # -- relationships ---------------------------------------------------
    profile: Mapped["Profile"] = relationship(back_populates="favorites")

    __table_args__ = (
        # Duplicate prevention: a user cannot favourite the same provider
        # track twice.
        UniqueConstraint(
            "user_id",
            "provider",
            "provider_track_id",
            name="uk_favorites_user_provider_track",
        ),
        # Listing a user's favourites, newest first.  The unique constraint
        # above already covers plain ``user_id`` lookups because ``user_id``
        # is its leading column.
        Index("idx_favorites_user_created_at", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Favorite user_id={self.user_id} "
            f"provider={self.provider}:{self.provider_track_id}>"
        )
