"""
Styles Router

Manages trained styles and prompt writing functionality.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import base64
from io import BytesIO
from PIL import Image

from backend.database import get_db
from backend.models.db_models import TrainedStyle, Session, StyleProfileDB, Iteration, GenerationHistory
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
    GenerationHistoryResponse,
)
from backend.services.storage import storage_service
from backend.services.prompt_writer import prompt_writer
from backend.services.comfyui import comfyui_service
from backend.services.abstractor import style_abstractor

router = APIRouter(prefix="/api/styles", tags=["styles"])
logger = logging.getLogger(__name__)


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


def build_training_summary(
    style_profile: StyleProfile,
    iteration_history: list[dict],
    style_rules: StyleRules,
) -> dict:
    """
    Build a comprehensive summary of what the agent learned during training.
    This captures the 'personality' of this style agent.
    """
    from collections import Counter

    summary = {
        "style_name": style_profile.style_name,
        "original_subject": style_profile.original_subject,
        "iterations_total": len(iteration_history),
        "iterations_approved": 0,
        "iterations_rejected": 0,
        "average_score": None,
        "dimension_scores": {},
        "strengths": [],
        "weaknesses": [],
        "key_traits": [],
        "learned_rules": {
            "always_include": style_rules.always_include,
            "always_avoid": style_rules.always_avoid,
            "technique": style_rules.technique_keywords,
            "mood": style_rules.mood_keywords,
            "emphasize": style_rules.emphasize,
            "de_emphasize": style_rules.de_emphasize,
        },
        "palette_summary": {
            "dominant_colors": style_profile.palette.dominant_colors[:5],
            "color_descriptions": style_profile.palette.color_descriptions[:5],
            "saturation": style_profile.palette.saturation,
            "value_range": style_profile.palette.value_range,
        },
        "lighting_summary": {
            "type": style_profile.lighting.lighting_type,
            "shadows": style_profile.lighting.shadows,
            "highlights": style_profile.lighting.highlights,
        },
        "composition_summary": {
            "camera": style_profile.composition.camera,
            "framing": style_profile.composition.framing,
        },
    }

    # Process iteration history
    all_scores = []
    dimension_scores = {}
    all_preserved = []
    all_lost = []

    for iteration in iteration_history:
        if iteration.get("approved"):
            summary["iterations_approved"] += 1
        else:
            summary["iterations_rejected"] += 1

        if iteration.get("scores"):
            for dim, score in iteration["scores"].items():
                if dim not in dimension_scores:
                    dimension_scores[dim] = []
                dimension_scores[dim].append(score)
                if dim == "overall":
                    all_scores.append(score)

        if iteration.get("preserved_traits"):
            all_preserved.extend(iteration["preserved_traits"])
        if iteration.get("lost_traits"):
            all_lost.extend(iteration["lost_traits"])

    # Calculate averages
    if all_scores:
        summary["average_score"] = sum(all_scores) // len(all_scores)

    # Calculate dimension averages and identify strengths/weaknesses
    for dim, scores in dimension_scores.items():
        if dim == "overall":
            continue
        avg = sum(scores) // len(scores)
        summary["dimension_scores"][dim] = avg
        if avg >= 75:
            summary["strengths"].append(dim)
        elif avg < 60:
            summary["weaknesses"].append(dim)

    # Find key traits (most frequently preserved)
    preserved_counts = Counter(all_preserved)
    summary["key_traits"] = [
        trait for trait, count in preserved_counts.most_common(5)
    ]

    # Find problem areas (most frequently lost)
    lost_counts = Counter(all_lost)
    summary["problem_areas"] = [
        trait for trait, count in lost_counts.most_common(5)
    ]

    return summary


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
        training_summary=style.training_summary_json,
        thumbnail_b64=style.thumbnail_b64,
        source_session_id=style.source_session_id,
        iterations_trained=style.iterations_trained,
        final_score=style.final_score,
        tags=style.tags_json or [],
        created_at=style.created_at,
        updated_at=style.updated_at,
    )


@router.post("/checkpoint", response_model=TrainedStyleResponse)
async def checkpoint_style(
    data: TrainedStyleCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a checkpoint of the current training state WITHOUT ending the session.

    This allows you to:
    - Save interim progress during training
    - Compare different training stages
    - Revert to earlier states if needed
    - Continue training after checkpoint

    The session remains active and you can continue iterating.
    """
    return await _create_style_snapshot(data, db, is_checkpoint=True)


@router.post("/finalize", response_model=TrainedStyleResponse)
async def finalize_style(
    data: TrainedStyleCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Finalize a training session into a reusable trained style.

    This creates a final production-ready style from your training session.
    The session remains intact - you can still continue training if needed,
    but this marks a style as "complete" for use in production.
    """
    return await _create_style_snapshot(data, db, is_checkpoint=False)


def sanitize_style_profile(profile: StyleProfile) -> StyleProfile:
    """
    Remove subject-specific information from a style profile.

    This ensures that finalized styles contain ONLY style metadata,
    not references to the training subject (e.g., "lion", "cat").
    """
    # Create a copy to avoid modifying original
    profile_dict = profile.model_dump()

    # Remove subject-specific fields
    profile_dict["original_subject"] = None
    profile_dict["suggested_test_prompt"] = None
    profile_dict["image_description"] = None

    # Filter subject-specific terms from core_invariants
    subject_keywords = [
        "cat", "dog", "lion", "tiger", "bear", "wolf", "fox", "rabbit", "deer",
        "person", "human", "woman", "man", "child", "baby", "face", "portrait",
        "animal", "bird", "fish", "creature", "dragon", "monster",
        "tree", "forest", "mountain", "ocean", "sky", "cloud", "sun", "moon",
        "car", "vehicle", "building", "house", "city", "landscape",
        "facing", "centered", "standing", "sitting", "lying", "walking", "running",
        "positioned", "placed", "located", "foreground", "background", "middle ground",
        "subject", "figure", "character", "main", "central",
        "left", "right", "front", "back", "side view", "profile",
        "expression", "eyes", "gaze", "look", "stare", "mouth", "nose", "ears",
        "mane", "fur", "tail", "paw", "claw", "wing", "beak", "feather",
        "silhouette", "pose", "posture", "stance",
        "sleeping", "resting", "awake", "alert", "majestic", "regal", "elegant",
        "lion's", "cat's", "dog's", "fox's", "bird's", "person's", "bunny",
        "head", "body", "form"  # added generic anatomy
    ]

    def contains_subject(text: str) -> bool:
        """Check if text contains subject-specific keywords."""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in subject_keywords)

    def sanitize_text(text: str) -> str:
        """Return empty string if text contains subject keywords."""
        return "" if contains_subject(text) else text

    # Filter core_invariants (list of strings)
    filtered_invariants = [
        inv for inv in profile_dict.get("core_invariants", [])
        if not contains_subject(inv)
    ]
    profile_dict["core_invariants"] = filtered_invariants

    # Sanitize nested lighting fields
    if "lighting" in profile_dict and profile_dict["lighting"]:
        lighting = profile_dict["lighting"]
        lighting["lighting_type"] = sanitize_text(lighting.get("lighting_type", ""))
        lighting["shadows"] = sanitize_text(lighting.get("shadows", ""))
        lighting["highlights"] = sanitize_text(lighting.get("highlights", ""))

    # Sanitize nested line_and_shape fields
    if "line_and_shape" in profile_dict and profile_dict["line_and_shape"]:
        line_shape = profile_dict["line_and_shape"]
        line_shape["line_quality"] = sanitize_text(line_shape.get("line_quality", ""))
        line_shape["shape_language"] = sanitize_text(line_shape.get("shape_language", ""))
        line_shape["geometry_notes"] = sanitize_text(line_shape.get("geometry_notes", ""))

    # Sanitize nested texture fields
    if "texture" in profile_dict and profile_dict["texture"]:
        texture = profile_dict["texture"]
        texture["surface"] = sanitize_text(texture.get("surface", ""))

    # Sanitize nested composition fields
    if "composition" in profile_dict and profile_dict["composition"]:
        comp = profile_dict["composition"]
        comp["framing"] = sanitize_text(comp.get("framing", ""))
        comp["depth"] = sanitize_text(comp.get("depth", ""))
        comp["negative_space_behavior"] = sanitize_text(comp.get("negative_space_behavior", ""))
        comp["structural_notes"] = sanitize_text(comp.get("structural_notes", ""))

    # Sanitize motifs.recurring_elements (list)
    if "motifs" in profile_dict and profile_dict["motifs"]:
        motifs = profile_dict["motifs"]
        if "recurring_elements" in motifs:
            motifs["recurring_elements"] = [
                elem for elem in motifs.get("recurring_elements", [])
                if not contains_subject(elem)
            ]

    return StyleProfile(**profile_dict)


def sanitize_style_rules(rules: StyleRules) -> StyleRules:
    """
    Remove subject-specific information from style rules.

    This filters out subject references that may have leaked from:
    - core_invariants (before sanitization)
    - iteration history (lost_traits, preserved_traits from critique)
    """
    rules_dict = rules.model_dump()

    # Same keywords as profile sanitization
    subject_keywords = [
        "cat", "dog", "lion", "tiger", "bear", "wolf", "fox", "rabbit", "deer",
        "person", "human", "woman", "man", "child", "baby", "face", "portrait",
        "animal", "bird", "fish", "creature", "dragon", "monster",
        "tree", "forest", "mountain", "ocean", "sky", "cloud", "sun", "moon",
        "car", "vehicle", "building", "house", "city", "landscape",
        "facing", "centered", "standing", "sitting", "lying", "walking", "running",
        "positioned", "placed", "located", "foreground", "background", "middle ground",
        "subject", "figure", "character", "main", "central",
        "left", "right", "front", "back", "side view", "profile",
        "expression", "eyes", "gaze", "look", "stare", "mouth", "nose", "ears",
        "mane", "fur", "tail", "paw", "claw", "wing", "beak", "feather",
        "silhouette", "pose", "posture", "stance",
        "sleeping", "resting", "awake", "alert", "majestic", "regal", "elegant",
        "lion's", "cat's", "dog's", "fox's", "bird's", "person's", "bunny",
        "head", "body", "form"  # possessives and generic anatomy
    ]

    def filter_list(items: list[str]) -> list[str]:
        """Filter subject-specific items from a list."""
        filtered = []
        for item in items:
            item_lower = item.lower()
            is_subject_specific = any(keyword in item_lower for keyword in subject_keywords)
            if not is_subject_specific:
                filtered.append(item)
        return filtered

    # Filter all list fields that might contain subject data
    if rules_dict.get("always_include"):
        rules_dict["always_include"] = filter_list(rules_dict["always_include"])

    if rules_dict.get("emphasize"):
        rules_dict["emphasize"] = filter_list(rules_dict["emphasize"])

    if rules_dict.get("de_emphasize"):
        rules_dict["de_emphasize"] = filter_list(rules_dict["de_emphasize"])

    # always_avoid and forbidden_elements should be fine - they're about what NOT to include
    # But sanitize them anyway for completeness
    if rules_dict.get("always_avoid"):
        rules_dict["always_avoid"] = filter_list(rules_dict["always_avoid"])

    return StyleRules(**rules_dict)


async def _create_style_snapshot(
    data: TrainedStyleCreate,
    db: AsyncSession,
    is_checkpoint: bool = False,
):
    """
    Internal function to create a style snapshot (checkpoint or finalization).
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
    style_profile_raw = StyleProfile(**latest_profile_db.profile_json)

    # Abstract: use VLM to convert subject-specific descriptions to generic style rules
    logger.info(f"[finalize] Abstracting style profile to remove subject references...")
    style_profile = await style_abstractor.abstract_style_profile(style_profile_raw)

    # Gather FULL iteration history with critique data
    iteration_history = []
    for it in session.iterations:
        if it.approved is not None:
            iteration_data = {
                "iteration_num": it.iteration_num,
                "approved": it.approved,
                "notes": it.feedback,
                "scores": it.scores_json or {},
                "prompt_used": it.prompt_used,
            }
            # Add critique data if available
            if it.critique_json:
                iteration_data["preserved_traits"] = it.critique_json.get("preserved_traits", [])
                iteration_data["lost_traits"] = it.critique_json.get("lost_traits", [])
                iteration_data["interesting_mutations"] = it.critique_json.get("interesting_mutations", [])
            iteration_history.append(iteration_data)

    # Extract style rules with full iteration data
    style_rules_raw = prompt_writer.extract_rules_from_profile(
        style_profile, iteration_history
    )

    # Sanitize: remove subject-specific information from rules
    # (may have leaked from iteration history critique data)
    style_rules = sanitize_style_rules(style_rules_raw)

    # Calculate final score from last iteration
    final_score = None
    if session.iterations:
        last_iteration = max(session.iterations, key=lambda i: i.iteration_num)
        if last_iteration.scores_json and "overall" in last_iteration.scores_json:
            final_score = last_iteration.scores_json["overall"]

    # Build training summary - what this agent learned
    training_summary = build_training_summary(
        style_profile, iteration_history, style_rules
    )

    # Create thumbnail from best iteration (highest scoring approved, or latest)
    thumbnail = None
    best_iteration = None

    # Find best iteration: highest scoring approved iteration
    if session.iterations:
        approved_iterations = [it for it in session.iterations if it.approved]
        if approved_iterations:
            # Get highest scoring approved iteration
            best_iteration = max(
                approved_iterations,
                key=lambda it: it.scores_json.get("overall", 0) if it.scores_json else 0
            )
        else:
            # No approved iterations - use latest
            best_iteration = max(session.iterations, key=lambda it: it.iteration_num)

    # Create thumbnail from best iteration's image
    if best_iteration and best_iteration.image_path:
        try:
            image_b64 = await storage_service.load_image_raw(best_iteration.image_path)
            thumbnail = create_thumbnail(image_b64)
        except Exception:
            # Fallback to original if iteration image fails
            if session.original_image_path:
                try:
                    image_b64 = await storage_service.load_image_raw(session.original_image_path)
                    thumbnail = create_thumbnail(image_b64)
                except Exception:
                    pass

    # Build name with checkpoint indicator if needed
    display_name = data.name
    tags_with_type = list(data.tags) if data.tags else []

    if is_checkpoint:
        # Add checkpoint indicator
        if not display_name.startswith("[CHECKPOINT]"):
            display_name = f"[CHECKPOINT] {data.name}"
        if "checkpoint" not in tags_with_type:
            tags_with_type.append("checkpoint")
    else:
        if "finalized" not in tags_with_type:
            tags_with_type.append("finalized")

    # Create the trained style (agent)
    trained_style = TrainedStyle(
        name=display_name,
        description=data.description,
        style_profile_json=style_profile.model_dump(),
        style_rules_json=style_rules.model_dump(),
        training_summary_json=training_summary,
        thumbnail_b64=thumbnail,
        source_session_id=session.id,
        iterations_trained=len(session.iterations),
        final_score=final_score,
        tags_json=tags_with_type,
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
        training_summary=training_summary,
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
        training_summary=style.training_summary_json,
        thumbnail_b64=style.thumbnail_b64,
        source_session_id=style.source_session_id,
        iterations_trained=style.iterations_trained,
        final_score=style.final_score,
        tags=style.tags_json or [],
        created_at=style.created_at,
        updated_at=style.updated_at,
    )


@router.delete("/bulk/all")
async def delete_all_styles(db: AsyncSession = Depends(get_db)):
    """Delete ALL trained styles. Use with caution!"""
    # Get all styles
    result = await db.execute(select(TrainedStyle))
    styles = result.scalars().all()

    deleted_count = 0
    for style in styles:
        try:
            await db.delete(style)
            deleted_count += 1
        except Exception as e:
            print(f"Failed to delete style {style.id}: {e}")

    await db.commit()

    return {
        "status": "deleted",
        "count": deleted_count,
        "message": f"Deleted {deleted_count} trained styles"
    }


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

    return await prompt_writer.write_prompt(
        style_profile=style_profile,
        style_rules=style_rules,
        subject=data.subject,
        additional_context=data.additional_context,
        include_negative=data.include_negative,
        variation_level=data.variation_level,
        use_creative_rewrite=data.use_creative_rewrite,
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
    prompt_result = await prompt_writer.write_prompt(
        style_profile=style_profile,
        style_rules=style_rules,
        subject=data.subject,
        additional_context=data.additional_context,
        include_negative=True,
        variation_level=data.variation_level,
        use_creative_rewrite=data.use_creative_rewrite,
    )

    # Generate the image
    image_b64 = await comfyui_service.generate(
        prompt=prompt_result.positive_prompt,
        negative_prompt=prompt_result.negative_prompt,
    )

    # Save the generated image to storage
    image_path = None
    try:
        image_filename = f"gen_{style.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        saved_path = await storage_service.save_image(style.id, image_b64, image_filename)
        image_path = str(saved_path)
    except Exception as e:
        logger.warning(f"Failed to save generated image: {e}")

    # Save to generation history
    history_entry = GenerationHistory(
        style_id=style.id,
        style_name=style.name,
        subject=data.subject,
        additional_context=data.additional_context,
        positive_prompt=prompt_result.positive_prompt,
        negative_prompt=prompt_result.negative_prompt,
        image_path=image_path,
    )
    db.add(history_entry)
    await db.commit()

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
        prompt_result = await prompt_writer.write_prompt(
            style_profile=style_profile,
            style_rules=style_rules,
            subject=subject,
            include_negative=True,
        )
        results.append(prompt_result)

    return results


@router.post("/{style_id}/regenerate-thumbnail")
async def regenerate_thumbnail(
    style_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate thumbnail for a trained style using best iteration.
    Useful for updating styles created before thumbnail fix.
    """
    # Get the style
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    if not style.source_session_id:
        raise HTTPException(status_code=400, detail="Style has no source session")

    # Get the source session with iterations
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.iterations))
        .where(Session.id == style.source_session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Source session not found")

    # Find best iteration (same logic as finalize)
    thumbnail = None
    best_iteration = None

    if session.iterations:
        approved_iterations = [it for it in session.iterations if it.approved]
        if approved_iterations:
            best_iteration = max(
                approved_iterations,
                key=lambda it: it.scores_json.get("overall", 0) if it.scores_json else 0
            )
        else:
            best_iteration = max(session.iterations, key=lambda it: it.iteration_num)

    # Create thumbnail from best iteration's image
    if best_iteration and best_iteration.image_path:
        try:
            image_b64 = await storage_service.load_image_raw(best_iteration.image_path)
            thumbnail = create_thumbnail(image_b64)
        except Exception as e:
            logger.warning(f"Failed to load iteration image: {e}")
            # Fallback to original if iteration image fails
            if session.original_image_path:
                try:
                    image_b64 = await storage_service.load_image_raw(session.original_image_path)
                    thumbnail = create_thumbnail(image_b64)
                except Exception as e:
                    logger.warning(f"Failed to load original image: {e}")

    if thumbnail:
        style.thumbnail_b64 = thumbnail
        await db.commit()
        await db.refresh(style)
        return {"status": "success", "message": "Thumbnail regenerated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to generate thumbnail")


@router.get("/{style_id}/history", response_model=list[GenerationHistoryResponse])
async def get_generation_history(
    style_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Get generation history for a trained style.
    Returns the most recent generations with their prompts and images.
    """
    # Verify style exists
    result = await db.execute(
        select(TrainedStyle).where(TrainedStyle.id == style_id)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    # Get history entries
    result = await db.execute(
        select(GenerationHistory)
        .where(GenerationHistory.style_id == style_id)
        .order_by(GenerationHistory.created_at.desc())
        .limit(limit)
    )
    history_entries = result.scalars().all()

    # Load images and build responses
    responses = []
    for entry in history_entries:
        image_b64 = None
        if entry.image_path:
            try:
                image_b64 = await storage_service.load_image_raw(entry.image_path)
            except Exception as e:
                logger.warning(f"Failed to load image for history entry {entry.id}: {e}")

        responses.append(GenerationHistoryResponse(
            id=entry.id,
            style_id=entry.style_id,
            style_name=entry.style_name,
            subject=entry.subject,
            additional_context=entry.additional_context,
            positive_prompt=entry.positive_prompt,
            negative_prompt=entry.negative_prompt,
            image_b64=image_b64,
            created_at=entry.created_at,
        ))

    return responses
