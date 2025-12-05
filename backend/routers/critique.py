from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import (
    CritiqueRequest,
    CritiqueResult,
    StyleProfile,
    SessionStatus,
)
from backend.models.db_models import Session, StyleProfileDB, Iteration
from backend.services.storage import storage_service
from backend.services.critic import style_critic

router = APIRouter(prefix="/api/critique", tags=["critique"])


@router.post("/", response_model=CritiqueResult)
async def critique_iteration(
    data: CritiqueRequest,
    db: AsyncSession = Depends(get_db),
):
    """Critique a generated image against the original style."""
    # Get session
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get iteration
    result = await db.execute(
        select(Iteration).where(Iteration.id == data.iteration_id)
    )
    iteration = result.scalar_one_or_none()

    if not iteration:
        raise HTTPException(status_code=404, detail="Iteration not found")

    if not session.original_image_path:
        raise HTTPException(status_code=400, detail="No original image found")

    if not session.style_profiles:
        raise HTTPException(status_code=400, detail="No style profile found")

    # Get latest style profile
    latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
    style_profile = StyleProfile(**latest_profile_db.profile_json)

    # Update status
    session.status = SessionStatus.CRITIQUING.value
    await db.commit()

    try:
        # Load images
        original_b64 = await storage_service.load_image_raw(
            session.original_image_path
        )
        generated_b64 = await storage_service.load_image_raw(iteration.image_path)

        # Run critique
        critique_result = await style_critic.critique(
            original_image_b64=original_b64,
            generated_image_b64=generated_b64,
            style_profile=style_profile,
            creativity_level=data.creativity_level,
        )

        # Update iteration with scores
        iteration.scores_json = critique_result.match_scores

        session.status = SessionStatus.READY.value
        await db.commit()

        return critique_result

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply")
async def apply_critique(
    session_id: str,
    critique_result: CritiqueResult,
    db: AsyncSession = Depends(get_db),
):
    """Apply critique results and create a new style profile version."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine new version number
    current_version = max(
        (sp.version for sp in session.style_profiles), default=0
    )
    new_version = current_version + 1

    # Create new style profile
    new_profile = StyleProfileDB(
        session_id=session_id,
        version=new_version,
        profile_json=critique_result.updated_style_profile.model_dump(),
    )
    db.add(new_profile)
    await db.commit()

    return {
        "version": new_version,
        "profile": critique_result.updated_style_profile.model_dump(),
    }
