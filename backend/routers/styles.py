"""
Styles Router

Manages trained styles and prompt writing functionality.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import base64
from io import BytesIO
from PIL import Image

from backend.database import get_db
from backend.models.db_models import TrainedStyle, Session, StyleProfileDB, Iteration
from backend.models.schemas import (
    StyleProfile,
    StyleRules,
    TrainedStyleCreate,
    TrainedStyleResponse,
    TrainedStyleSummary,
    PromptWriteRequest,
    PromptWriteResponse,
    PromptGenerateRequest,
    PromptGenerateResponse,
)
from backend.services.storage import storage_service
from backend.services.prompt_writer import prompt_writer
from backend.services.comfyui import comfyui_service

router = APIRouter(prefix="/api/styles", tags=["styles"])


def create_thumbnail(image_b64: str, size: tuple = (128, 128)) -> str:
    """Create a small thumbnail from a base64 image."""
    # Remove data URL prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    image_data = base64.b64decode(image_b64)
    image = Image.open(BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    # Create thumbnail
    image.thumbnail(size, Image.Resampling.LANCZOS)

    # Save to base64
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


@router.get("/", response_model=list[TrainedStyleSummary])
async def list_styles(
    db: AsyncSession = Depends(get_db),
    tag: str | None = None,
):
    """List all trained styles, optionally filtered by tag."""
    query = select(TrainedStyle).order_by(TrainedStyle.created_at.desc())

    result = await db.execute(query)
    styles = result.scalars().all()

    # Filter by tag if provided
    if tag:
        styles = [s for s in styles if tag in (s.tags_json or [])]

    return [
        TrainedStyleSummary(
            id=s.id,
            name=s.name,
            description=s.description,
            thumbnail_b64=s.thumbnail_b64,
            iterations_trained=s.iterations_trained,
            final_score=s.final_score,
            tags=s.tags_json or [],
            created_at=s.created_at,
        )
        for s in styles
    ]


@router.get("/{style_id}", response_model=TrainedStyleResponse)
async def get_style(
    style_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a trained style by ID."""
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    return TrainedStyleResponse(
        id=style.id,
        name=style.name,
        description=style.description,
        style_profile=StyleProfile(**style.style_profile_json),
        style_rules=StyleRules(**style.style_rules_json),
        thumbnail_b64=style.thumbnail_b64,
        source_session_id=style.source_session_id,
        iterations_trained=style.iterations_trained,
        final_score=style.final_score,
        tags=style.tags_json or [],
        created_at=style.created_at,
        updated_at=style.updated_at,
    )


@router.post("/finalize", response_model=TrainedStyleResponse)
async def finalize_style(
    data: TrainedStyleCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Finalize a training session into a reusable trained style.
    Extracts the latest style profile and generates style rules.
    """
    # Get the session with all related data
    result = await db.execute(
        select(Session)
        .options(
            selectinload(Session.style_profiles),
            selectinload(Session.iterations),
        )
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        raise HTTPException(status_code=400, detail="Session has no style profile")

    # Get the latest style profile
    latest_profile_db = max(session.style_profiles, key=lambda p: p.version)
    style_profile = StyleProfile(**latest_profile_db.profile_json)

    # Gather feedback history from iterations
    feedback_history = [
        {"approved": it.approved, "notes": it.feedback}
        for it in session.iterations
        if it.approved is not None
    ]

    # Extract style rules
    style_rules = prompt_writer.extract_rules_from_profile(
        style_profile, feedback_history
    )

    # Calculate final score from last iteration
    final_score = None
    if session.iterations:
        last_iteration = max(session.iterations, key=lambda i: i.iteration_num)
        if last_iteration.scores_json and "overall" in last_iteration.scores_json:
            final_score = last_iteration.scores_json["overall"]

    # Create thumbnail from original image
    thumbnail = None
    if session.original_image_path:
        try:
            image_b64 = await storage_service.load_image_raw(session.original_image_path)
            thumbnail = create_thumbnail(image_b64)
        except Exception:
            pass

    # Create the trained style
    trained_style = TrainedStyle(
        name=data.name,
        description=data.description,
        style_profile_json=style_profile.model_dump(),
        style_rules_json=style_rules.model_dump(),
        thumbnail_b64=thumbnail,
        source_session_id=session.id,
        iterations_trained=len(session.iterations),
        final_score=final_score,
        tags_json=data.tags,
    )

    db.add(trained_style)
    await db.commit()
    await db.refresh(trained_style)

    return TrainedStyleResponse(
        id=trained_style.id,
        name=trained_style.name,
        description=trained_style.description,
        style_profile=style_profile,
        style_rules=style_rules,
        thumbnail_b64=trained_style.thumbnail_b64,
        source_session_id=trained_style.source_session_id,
        iterations_trained=trained_style.iterations_trained,
        final_score=trained_style.final_score,
        tags=trained_style.tags_json or [],
        created_at=trained_style.created_at,
        updated_at=trained_style.updated_at,
    )


@router.delete("/{style_id}")
async def delete_style(
    style_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a trained style."""
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    await db.delete(style)
    await db.commit()

    return {"status": "deleted"}


@router.put("/{style_id}", response_model=TrainedStyleResponse)
async def update_style(
    style_id: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a trained style's metadata."""
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    if name is not None:
        style.name = name
    if description is not None:
        style.description = description
    if tags is not None:
        style.tags_json = tags

    await db.commit()
    await db.refresh(style)

    return TrainedStyleResponse(
        id=style.id,
        name=style.name,
        description=style.description,
        style_profile=StyleProfile(**style.style_profile_json),
        style_rules=StyleRules(**style.style_rules_json),
        thumbnail_b64=style.thumbnail_b64,
        source_session_id=style.source_session_id,
        iterations_trained=style.iterations_trained,
        final_score=style.final_score,
        tags=style.tags_json or [],
        created_at=style.created_at,
        updated_at=style.updated_at,
    )


# ============================================================
# Prompt Writer Endpoints
# ============================================================

@router.post("/write-prompt", response_model=PromptWriteResponse)
async def write_prompt(
    data: PromptWriteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Write a styled prompt using a trained style.
    Returns the prompt ready for use in any image generation system.
    """
    # Get the trained style
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == data.style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    style_profile = StyleProfile(**style.style_profile_json)
    style_rules = StyleRules(**style.style_rules_json)

    return prompt_writer.write_prompt(
        style_profile=style_profile,
        style_rules=style_rules,
        subject=data.subject,
        additional_context=data.additional_context,
        include_negative=data.include_negative,
    )


@router.post("/write-and-generate", response_model=PromptGenerateResponse)
async def write_and_generate(
    data: PromptGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Write a styled prompt AND generate an image using ComfyUI.
    """
    # Get the trained style
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == data.style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    style_profile = StyleProfile(**style.style_profile_json)
    style_rules = StyleRules(**style.style_rules_json)

    # Write the prompt
    prompt_result = prompt_writer.write_prompt(
        style_profile=style_profile,
        style_rules=style_rules,
        subject=data.subject,
        additional_context=data.additional_context,
        include_negative=True,
    )

    # Generate the image
    image_b64 = await comfyui_service.generate(
        prompt=prompt_result.positive_prompt,
        negative_prompt=prompt_result.negative_prompt,
    )

    return PromptGenerateResponse(
        positive_prompt=prompt_result.positive_prompt,
        negative_prompt=prompt_result.negative_prompt,
        image_b64=image_b64,
        style_name=style_profile.style_name,
    )


@router.post("/batch-write", response_model=list[PromptWriteResponse])
async def batch_write_prompts(
    style_id: str,
    subjects: list[str],
    db: AsyncSession = Depends(get_db),
):
    """
    Write multiple styled prompts at once.
    Useful for batch generation workflows.
    """
    # Get the trained style
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    style_profile = StyleProfile(**style.style_profile_json)
    style_rules = StyleRules(**style.style_rules_json)

    results = []
    for subject in subjects:
        prompt_result = prompt_writer.write_prompt(
            style_profile=style_profile,
            style_rules=style_rules,
            subject=subject,
            include_negative=True,
        )
        results.append(prompt_result)

    return results
