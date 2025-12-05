from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import (
    GenerationRequest,
    GenerationResponse,
    StyleProfile,
    SessionStatus,
)
from backend.models.db_models import Session, StyleProfileDB, Iteration
from backend.services.storage import storage_service
from backend.services.agent import style_agent
from backend.services.comfyui import comfyui_service

router = APIRouter(prefix="/api/generate", tags=["generation"])


@router.post("/", response_model=GenerationResponse)
async def generate_image(
    data: GenerationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate an image using the current style agent."""
    # Get session with profiles and iterations
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        raise HTTPException(
            status_code=400, detail="No style profile found. Run extraction first."
        )

    # Get latest style profile
    latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
    style_profile = StyleProfile(**latest_profile_db.profile_json)

    # Gather feedback history from previous iterations
    feedback_history = [
        {"iteration": it.iteration_num, "notes": it.feedback}
        for it in session.iterations
        if it.feedback
    ]

    # Update status
    session.status = SessionStatus.GENERATING.value
    await db.commit()

    try:
        # Generate image prompt using the style agent
        image_prompt = await style_agent.generate_image_prompt(
            style_profile=style_profile,
            subject=data.subject,
            feedback_history=feedback_history,
        )

        # Generate image using ComfyUI
        image_b64 = await comfyui_service.generate(prompt=image_prompt)

        # Determine iteration number
        iteration_num = len(session.iterations) + 1

        # Save image to disk
        filename = storage_service.get_iteration_filename(iteration_num)
        image_path = await storage_service.save_image(
            session.id, image_b64, filename
        )

        # Create iteration record
        iteration = Iteration(
            session_id=session.id,
            iteration_num=iteration_num,
            image_path=str(image_path),
            prompt_used=image_prompt,
        )
        db.add(iteration)

        session.status = SessionStatus.READY.value
        await db.commit()
        await db.refresh(iteration)

        # Return with data URL prefix for frontend
        image_b64_with_prefix = f"data:image/png;base64,{image_b64}"

        return GenerationResponse(
            iteration_id=iteration.id,
            image_b64=image_b64_with_prefix,
            prompt_used=image_prompt,
        )

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompt-preview")
async def preview_prompt(
    session_id: str,
    subject: str,
    db: AsyncSession = Depends(get_db),
):
    """Preview what prompt would be generated without actually generating an image."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        raise HTTPException(status_code=400, detail="No style profile found")

    latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
    style_profile = StyleProfile(**latest_profile_db.profile_json)

    feedback_history = [
        {"iteration": it.iteration_num, "notes": it.feedback}
        for it in session.iterations
        if it.feedback
    ]

    image_prompt = await style_agent.generate_image_prompt(
        style_profile=style_profile,
        subject=subject,
        feedback_history=feedback_history,
    )

    return {"prompt": image_prompt}
