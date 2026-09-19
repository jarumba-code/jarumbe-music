"""Playlist endpoints — owner-scoped mutations, public visibility for reads.

Rate limiting is attached at the route level (``dependencies=[...]``), which
FastAPI resolves before the endpoint's own parameters — so the limiter runs
before JWT verification and an invalid token is charged to the anonymous (IP)
bucket instead of bypassing the limiter.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import PaginationParams, rate_limiter
from app.api.routes.auth import get_current_user_id
from app.database import get_db
from app.models.playlist import Playlist
from app.schemas.playlist import PlaylistCreate, PlaylistRead, PlaylistUpdate
from app.services.auth import ensure_profile_exists

router = APIRouter()


def _load_playlist_for_read(
    db: Session, playlist_id: UUID, user_id: str
) -> Playlist:
    """Owner or public-visibility read; generic 404 otherwise (no existence leak)."""
    playlist = db.get(Playlist, str(playlist_id))
    if playlist is None or (playlist.user_id != user_id and not playlist.is_public):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


def _load_owned_playlist(db: Session, playlist_id: UUID, user_id: str) -> Playlist:
    """Owner-only access for mutations; generic 404 otherwise."""
    playlist = db.get(Playlist, str(playlist_id))
    if playlist is None or playlist.user_id != user_id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


@router.get(
    "/playlists",
    response_model=list[PlaylistRead],
    dependencies=[Depends(rate_limiter("playlists"))],
)
def list_my_playlists(
    pagination: PaginationParams = Depends(),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[Playlist]:
    """The authenticated user's own playlists, newest first.

    Paginated: ``limit`` (1-100) and ``offset`` (>= 0) — never an unbounded
    result set.
    """
    return list(
        db.execute(
            select(Playlist)
            .where(Playlist.user_id == user_id)
            .order_by(Playlist.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        ).scalars()
    )


@router.post(
    "/playlists",
    response_model=PlaylistRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter("playlists"))],
)
def create_playlist(
    payload: PlaylistCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Playlist:
    """Create a playlist owned by the verified JWT identity.

    ``user_id`` is never accepted from the body.  The profile row is ensured
    first so the ``playlists.user_id -> profiles.id`` foreign key cannot fail
    for a brand-new verified user.
    """
    ensure_profile_exists(db, user_id)

    playlist = Playlist(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


@router.get(
    "/playlists/{playlist_id}",
    response_model=PlaylistRead,
    dependencies=[Depends(rate_limiter("playlists"))],
)
def get_playlist(
    playlist_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Playlist:
    """Read one playlist: the owner, or anyone for a public playlist.

    An invalid UUID is a 422 (path validation); any playlist the caller may not
    see is a plain 404, so private playlists do not leak their existence.
    """
    return _load_playlist_for_read(db, playlist_id, user_id)


@router.patch(
    "/playlists/{playlist_id}",
    response_model=PlaylistRead,
    dependencies=[Depends(rate_limiter("playlists"))],
)
def update_playlist(
    playlist_id: UUID,
    payload: PlaylistUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Playlist:
    """Only the owner can rename/re-scope a playlist — public visibility never
    grants modification rights.

    Omitted fields are left unchanged.  ``name`` / ``is_public`` are NOT NULL
    columns and the request schema rejects an explicit ``null`` for them with a
    422, so a patch can never reach the database with a value that violates a
    NOT NULL constraint.
    """
    playlist = _load_owned_playlist(db, playlist_id, user_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("name", "description", "is_public"):
        if field in changes:
            setattr(playlist, field, changes[field])
    db.commit()
    db.refresh(playlist)
    return playlist


@router.delete(
    "/playlists/{playlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limiter("playlists"))],
)
def delete_playlist(
    playlist_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete one of the caller's own playlists (and cascade to its tracks)."""
    playlist = _load_owned_playlist(db, playlist_id, user_id)
    db.delete(playlist)
    db.commit()
