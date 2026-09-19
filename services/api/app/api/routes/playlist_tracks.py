"""Playlist-track endpoints — reads follow playlist visibility, writes are owner-only.

The ownership/publicity decision is made on the *parent playlist*, so no
body/path parameter can grant access to another user's playlist content.

Concurrent appends
------------------
The next ``position`` is allocated in the same transaction that holds a row
lock on the parent playlist row (``SELECT ... FOR UPDATE`` where the dialect
supports it, i.e. PostgreSQL in production).  Two simultaneous appends cannot
both read the same ``max(position)``.  SQLite — the local test database — has
no row locks, so there the deferred unique constraint on
``(playlist_id, position)`` remains the backstop and a violation is mapped to
409 instead of a database error.

Rate limiting is attached at the route level (``dependencies=[...]``), which
FastAPI resolves before the endpoint's own parameters, so it runs before JWT
verification.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import PaginationParams, rate_limiter
from app.api.routes.auth import get_current_user_id
from app.database import get_db
from app.models.playlist import Playlist
from app.models.playlist_track import PlaylistTrack
from app.schemas.playlist_track import (
    PlaylistTrackCreate,
    PlaylistTrackRead,
    PlaylistTrackUpdate,
)

router = APIRouter()


def _load_playlist_for_read(db: Session, playlist_id: UUID, user_id: str) -> Playlist:
    playlist = db.get(Playlist, str(playlist_id))
    if playlist is None or (playlist.user_id != user_id and not playlist.is_public):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


def _load_owned_playlist(db: Session, playlist_id: UUID, user_id: str) -> Playlist:
    playlist = db.get(Playlist, str(playlist_id))
    if playlist is None or playlist.user_id != user_id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


def _load_owned_playlist_for_update(
    db: Session, playlist_id: UUID, user_id: str
) -> Playlist:
    """Owner-only access, taking a write lock on the playlist row.

    PostgreSQL supports ``SELECT ... FOR UPDATE``; SQLite does not, and
    SQLAlchemy omits the clause for that dialect.  The lock serializes
    concurrent appends to the same playlist for the duration of the
    transaction, while the uniqueness constraints stay in place as the final
    guarantee.
    """
    statement = select(Playlist).where(Playlist.id == str(playlist_id))
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    playlist = db.execute(statement).scalar_one_or_none()
    if playlist is None or playlist.user_id != user_id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


@router.get(
    "/playlists/{playlist_id}/tracks",
    response_model=list[PlaylistTrackRead],
    dependencies=[Depends(rate_limiter("playlist_tracks"))],
)
def list_playlist_tracks(
    playlist_id: UUID,
    pagination: PaginationParams = Depends(),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[PlaylistTrack]:
    """Ordered track listing for an owned or public playlist (paginated)."""
    _load_playlist_for_read(db, playlist_id, user_id)
    return list(
        db.execute(
            select(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == str(playlist_id))
            .order_by(PlaylistTrack.position)
            .offset(pagination.offset)
            .limit(pagination.limit)
        ).scalars()
    )


@router.post(
    "/playlists/{playlist_id}/tracks",
    response_model=PlaylistTrackRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter("playlist_tracks"))],
)
def add_playlist_track(
    playlist_id: UUID,
    payload: PlaylistTrackCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PlaylistTrack:
    """Append/insert a track into an *owned* playlist.

    A duplicate ``(playlist, provider, provider_track_id)`` is a 409, as is a
    position collision.  When ``position`` is omitted the entry is appended
    after the current last position, computed while holding a playlist row
    lock so concurrent appends cannot collide.
    """
    _load_owned_playlist_for_update(db, playlist_id, user_id)

    duplicate = db.execute(
        select(PlaylistTrack.id).where(
            PlaylistTrack.playlist_id == str(playlist_id),
            PlaylistTrack.provider == payload.provider,
            PlaylistTrack.provider_track_id == payload.provider_track_id,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Track is already in this playlist",
        )

    position = payload.position
    if position is None:
        last = db.execute(
            select(func.max(PlaylistTrack.position)).where(
                PlaylistTrack.playlist_id == str(playlist_id)
            )
        ).scalar()
        position = (last + 1) if last is not None else 0

    track = PlaylistTrack(
        playlist_id=str(playlist_id),
        position=position,
        provider=payload.provider,
        provider_track_id=payload.provider_track_id,
        title=payload.title,
        artist=payload.artist,
        album=payload.album,
        duration=payload.duration,
        artwork_url=payload.artwork_url,
        license_url=payload.license_url,
        license_name=payload.license_name,
    )
    db.add(track)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Track already in playlist or position already taken",
        ) from None
    db.refresh(track)
    return track


@router.patch(
    "/playlists/{playlist_id}/tracks/{track_id}",
    response_model=PlaylistTrackRead,
    dependencies=[Depends(rate_limiter("playlist_tracks"))],
)
def update_playlist_track(
    playlist_id: UUID,
    track_id: UUID,
    payload: PlaylistTrackUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PlaylistTrack:
    """Reorder one entry of an *owned* playlist.

    The track must belong to the playlist in the path (a track id from another
    playlist is a 404), ``position`` must be >= 0 (schema), and a position that
    is already taken is a 409.
    """
    _load_owned_playlist(db, playlist_id, user_id)
    track = db.get(PlaylistTrack, str(track_id))
    if track is None or track.playlist_id != str(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist track not found")
    track.position = payload.position
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Position already taken",
        ) from None
    db.refresh(track)
    return track


@router.delete(
    "/playlists/{playlist_id}/tracks/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limiter("playlist_tracks"))],
)
def delete_playlist_track(
    playlist_id: UUID,
    track_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Remove one entry from an *owned* playlist."""
    _load_owned_playlist(db, playlist_id, user_id)
    track = db.get(PlaylistTrack, str(track_id))
    if track is None or track.playlist_id != str(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist track not found")
    db.delete(track)
    db.commit()