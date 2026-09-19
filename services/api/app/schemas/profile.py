"""Pydantic schemas for user profiles.

A profile is Jarumba-specific presentation data attached to a Supabase Auth
user.  ``id`` **is** the ``auth.users.id`` UUID — Jarumba has no separate
identity system and never stores passwords or OAuth credentials.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel, _validate_optional_http_url


class ProfileRead(ORMModel):
    """Public representation of a Jarumba profile."""

    id: UUID = Field(..., description="Supabase Auth user UUID (auth.users.id)")
    display_name: Optional[str] = Field(default=None, description="Display name")
    avatar_url: Optional[str] = Field(default=None, description="Avatar image URL")
    created_at: datetime = Field(..., description="Row creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Row update timestamp (UTC)")


class ProfileUpdate(BaseModel):
    """Editable Jarumba-specific profile fields.

    Authentication data (email, password, OAuth tokens) belongs to Supabase
    Auth and is intentionally *not* editable through Jarumba.  Only the two
    Jarumba presentation fields below exist, so an unexpected key in the body
    is ignored rather than written (no mass assignment).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Display name; the database column is VARCHAR(255)",
    )
    avatar_url: Optional[str] = Field(
        default=None,
        description="Avatar image URL (absolute http(s) URL or null)",
    )

    @field_validator("display_name", mode="before")
    @classmethod
    def _blank_display_name_clears(cls, value: object) -> object:
        """A whitespace-only name clears the field instead of storing blanks."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("avatar_url", mode="before")
    @classmethod
    def _validate_avatar_url(cls, value: object) -> object:
        return _validate_optional_http_url(value, "avatar_url")


__all__ = ["ProfileRead", "ProfileUpdate"]