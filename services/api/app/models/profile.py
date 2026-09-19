"""Profile model — Jarumba-specific data for a Supabase Auth user."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Importing the stub registers ``auth.users`` in the shared metadata so the
# foreign key below can be resolved and rendered correctly in DDL.
from app.models.base import Base, utcnow
from app.models.external import auth_users  # noqa: F401

if TYPE_CHECKING:
    from app.models.favorite import Favorite
    from app.models.playlist import Playlist
    from app.models.recently_played import RecentlyPlayed


class Profile(Base):
    """Jarumba-specific profile for a Supabase Auth user.

    ``id`` **is** the ``auth.users.id`` value: there is a foreign key from
    ``profiles.id`` to ``auth.users.id`` and no independent identity system.
    This table holds only Jarumba-specific presentation data — never
    passwords, OAuth tokens, or other authentication credentials.
    """

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Same UUID as auth.users.id (supplied by Supabase Auth)",
    )
    display_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User-chosen display name",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="URL to the user's avatar image",
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
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    playlists: Mapped[list["Playlist"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recently_played: Mapped[list["RecentlyPlayed"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_profiles_display_name", "display_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Profile id={self.id} display_name={self.display_name!r}>"
