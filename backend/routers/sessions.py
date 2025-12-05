from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import SessionCreate, SessionResponse, SessionStatus
from backend.models.db_models import Session, StyleProfileDB, Iteration
from backend.services.storage import storage_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """List all sessions."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .order_by(Session.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            name=s.name,
            mode=s.mode,
            status=s.status,
            created_at=s.created_at,
            current_style_version=s.current_style_version,
            iteration_count=s.iteration_count,
        )
        for s in sessions
    ]


@router.post("/", response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new session with an original image."""
    session = Session(
        name=data.name,
        mode=data.mode.value,
        status=SessionStatus.CREATED.value,
    )
    db.add(session)
    await db.flush()

    # Save the original image
    image_path = await storage_service.save_image(
        session.id, data.image_b64, "original.png"
    )
    session.original_image_path = str(image_path)

    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        name=session.name,
        mode=session.mode,
        status=session.status,
        created_at=session.created_at,
        current_style_version=None,
        iteration_count=0,
    )


@router.get("/{session_id}", response_model=dict)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a session with all its data."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Load original image as base64
    original_image_b64 = None
    if session.original_image_path:
        try:
            original_image_b64 = await storage_service.load_image(
                session.original_image_path
            )
        except FileNotFoundError:
            pass

    # Get latest style profile
    latest_profile = None
    if session.style_profiles:
        latest = max(session.style_profiles, key=lambda sp: sp.version)
        latest_profile = {
            "version": latest.version,
            "profile": latest.profile_json,
            "created_at": latest.created_at.isoformat(),
        }

    # Get iterations with images
    iterations = []
    for it in sorted(session.iterations, key=lambda i: i.iteration_num):
        it_data = {
            "id": it.id,
            "iteration_num": it.iteration_num,
            "prompt_used": it.prompt_used,
            "scores": it.scores_json,
            "feedback": it.feedback,
            "approved": it.approved,
            "created_at": it.created_at.isoformat(),
        }
        try:
            it_data["image_b64"] = await storage_service.load_image(it.image_path)
        except FileNotFoundError:
            it_data["image_b64"] = None
        iterations.append(it_data)

    return {
        "id": session.id,
        "name": session.name,
        "mode": session.mode,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "original_image_b64": original_image_b64,
        "style_profile": latest_profile,
        "iterations": iterations,
    }


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a session and all its files."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete files
    storage_service.delete_session(session_id)

    # Delete from database
    await db.delete(session)
    await db.commit()

    return {"status": "deleted", "session_id": session_id}
