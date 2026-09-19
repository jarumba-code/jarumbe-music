"""RecentlyPlayed model — an append-only listening history entry.

History is **temporal**: the same user may play the same track repeatedly,
and every play is a meaningful record.  This table therefore has *no* unique
constraint on the track reference — only indexes to make "most recent plays
for this user" fast.
"""

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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.profile import Profile


class RecentlyPlayed(Base):
    """A single play event for a profile.

    Deliberately append-only: repeated plays of the same track create
    multiple rows ordered by ``played_at``.
    """

    __tablename__ = "recently_played"

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

    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=utcnow,
        comment="When the play event occurred",
    )

    # -- relationships ---------------------------------------------------
    profile: Mapped["Profile"] = relationship(back_populates="recently_played")

    __table_args__ = (
        # "Latest plays for this user".  PostgreSQL can scan a b-tree index
        # backwards, so an ascending index also serves ORDER BY played_at DESC.
        Index("idx_recently_played_user_played_at", "user_id", "played_at"),
        # "When did this user last play this specific provider track?"
        Index(
            "idx_recently_played_user_provider_track",
            "user_id",
            "provider",
            "provider_track_id",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<RecentlyPlayed user_id={self.user_id} "
            f"provider={self.provider}:{self.provider_track_id} played_at={self.played_at}>"
        )