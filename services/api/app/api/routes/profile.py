"""Current-user profile endpoints (identity from the verified JWT only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import rate_limiter
from app.api.routes.auth import get_current_user_id
from app.config import Settings, get_settings
from app.database import get_db
from app.models.profile import Profile
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.auth import ensure_profile_exists

router = APIRouter()


@router.get(
    "/profile",
    response_model=ProfileRead,
    dependencies=[Depends(rate_limiter("profile"))],
)
def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Profile:
    """The authenticated user's profile.

    The user id comes only from the verified JWT.  A verified user with no
    profile row yet self-heals: :func:`ensure_profile_exists` creates it
    (concurrent first requests are race-safe).
    """
    profile = db.execute(
        select(Profile).where(Profile.id == user_id)
    ).scalar_one_or_none()
    if profile is None:
        profile = ensure_profile_exists(db, user_id)
    return profile


@router.patch(
    "/profile",
    response_model=ProfileRead,
    dependencies=[Depends(rate_limiter("profile"))],
)
def update_my_profile(
    payload: ProfileUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Profile:
    """Update the two editable, Jarumba-owned profile fields.

    ``display_name`` and ``avatar_url`` are an explicit allow-list: identity
    (``id``) and any other key in the body are ignored, so the endpoint cannot
    be used for mass assignment.
    """
    profile = db.execute(
        select(Profile).where(Profile.id == user_id)
    ).scalar_one_or_none()
    if profile is None:
        profile = ensure_profile_exists(db, user_id)

    changes = payload.model_dump(exclude_unset=True)
    # Only explicitly permitted, Jarumba-specific fields are editable; the
    # primary key / identity can never be changed from the client.
    for field in ("display_name", "avatar_url"):
        if field in changes:
            setattr(profile, field, changes[field])
    db.commit()
    db.refresh(profile)
    return profile
