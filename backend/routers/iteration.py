import logging
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import (
    IterationRequest,
    FeedbackRequest,
    AutoModeRequest,
    AutoImproveRequest,
    StyleProfile,
    SessionStatus,
)
from backend.models.db_models import Session, StyleProfileDB, Iteration
from backend.services.storage import storage_service
from backend.services.agent import style_agent
from backend.services.comfyui import comfyui_service
from backend.services.critic import style_critic
from backend.services.auto_improver import auto_improver
from backend.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/iterate", tags=["iteration"])

# In-memory store for stop requests (session_id -> bool)
# This allows users to gracefully stop auto-improve loops via UI button
_stop_requests = {}


@router.post("/step")
async def run_iteration_step(
    data: IterationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run a single full iteration: generate image + critique."""
    session_id = data.session_id

    async def log(msg: str, level: str = "info", step: str = None):
        logger.info(f"[{step or 'iterate'}] {msg}")
        await manager.broadcast_log(session_id, msg, level, step)

    await log("Starting iteration step...", "info", "iterate")

    # Get session with all related data
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        await log("Session not found", "error", "iterate")
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        await log("No style profile found - extract style first", "error", "iterate")
        raise HTTPException(status_code=400, detail="No style profile found")

    if not session.original_image_path:
        await log("No original image found", "error", "iterate")
        raise HTTPException(status_code=400, detail="No original image found")

    # Get latest style profile
    latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
    style_profile = StyleProfile(**latest_profile_db.profile_json)
    await log(f"Using style profile v{latest_profile_db.version}: {style_profile.style_name}", "info", "iterate")

    # Gather FULL feedback history with approval status and critique data
    feedback_history = []
    for it in session.iterations:
        if it.approved is not None or it.feedback:
            entry = {
                "iteration": it.iteration_num,
                "approved": it.approved,
                "notes": it.feedback,
            }
            # Include critique data if available
            if it.critique_json:
                entry["preserved_traits"] = it.critique_json.get("preserved_traits", [])
                entry["lost_traits"] = it.critique_json.get("lost_traits", [])
            feedback_history.append(entry)

    if feedback_history:
        approved_count = sum(1 for f in feedback_history if f.get("approved"))
        rejected_count = sum(1 for f in feedback_history if f.get("approved") == False)
        await log(f"Loaded {len(feedback_history)} feedback entries ({approved_count} approved, {rejected_count} rejected)", "info", "iterate")

    try:
        # Step 1: Generate image prompt
        await log("Phase 1: Generating image prompt...", "info", "prompt")
        await manager.broadcast_progress(session_id, "prompt", 10, "Building prompt")
        session.status = SessionStatus.GENERATING.value
        await db.commit()

        await log(f"Subject: {data.subject}", "info", "prompt")
        await log(f"Creativity level: {data.creativity_level}/100", "info", "prompt")

        image_prompt = await style_agent.generate_image_prompt(
            style_profile=style_profile,
            subject=data.subject,
            feedback_history=feedback_history,
            session_id=session_id,
        )

        await log(f"Generated prompt ({len(image_prompt)} chars)", "success", "prompt")
        await log(f"Prompt: {image_prompt[:150]}...", "info", "prompt")
        await manager.broadcast_progress(session_id, "prompt", 25, "Prompt ready")

        # Step 2: Generate image
        await log("Phase 2: Generating image with ComfyUI...", "info", "generate")
        await manager.broadcast_progress(session_id, "generate", 30, "Sending to ComfyUI")

        image_b64 = await comfyui_service.generate(prompt=image_prompt, session_id=session_id)

        await log("Image generated successfully", "success", "generate")
        await manager.broadcast_progress(session_id, "generate", 50, "Image generated")

        # Save image
        iteration_num = len(session.iterations) + 1
        filename = storage_service.get_iteration_filename(iteration_num)
        image_path = await storage_service.save_image(
            session.id, image_b64, filename
        )
        await log(f"Saved iteration #{iteration_num} image", "info", "generate")

        # Create iteration record
        iteration = Iteration(
            session_id=session.id,
            iteration_num=iteration_num,
            image_path=str(image_path),
            prompt_used=image_prompt,
        )
        db.add(iteration)
        await db.flush()

        # Step 3: Critique
        await log("Phase 3: Critiquing generated image...", "info", "critique")
        await manager.broadcast_progress(session_id, "critique", 55, "Starting critique")
        session.status = SessionStatus.CRITIQUING.value
        await db.commit()

        await log("Loading original image for comparison...", "info", "critique")
        original_b64 = await storage_service.load_image_raw(
            session.original_image_path
        )

        await log("Sending images to VLM for style comparison...", "info", "critique")
        await manager.broadcast_progress(session_id, "critique", 60, "Analyzing style match")

        critique_result = await style_critic.critique(
            original_image_b64=original_b64,
            generated_image_b64=image_b64,
            style_profile=style_profile,
            creativity_level=data.creativity_level,
            session_id=session_id,
        )

        # Log critique results
        overall_score = critique_result.match_scores.get("overall", 0)
        await log(f"Critique complete - Overall score: {overall_score}/100", "success", "critique")
        await manager.broadcast_progress(session_id, "critique", 90, f"Score: {overall_score}/100")

        if critique_result.preserved_traits:
            await log(f"Preserved: {', '.join(critique_result.preserved_traits[:3])}", "info", "critique")
        if critique_result.lost_traits:
            await log(f"Lost: {', '.join(critique_result.lost_traits[:3])}", "warning", "critique")

        # Update iteration with scores AND full critique data
        iteration.scores_json = critique_result.match_scores
        iteration.critique_json = {
            "preserved_traits": critique_result.preserved_traits,
            "lost_traits": critique_result.lost_traits,
            "interesting_mutations": critique_result.interesting_mutations,
        }

        session.status = SessionStatus.READY.value
        await db.commit()
        await db.refresh(iteration)

        await log("Iteration complete!", "success", "iterate")
        await manager.broadcast_progress(session_id, "complete", 100, "Done")
        await manager.broadcast_complete(session_id)

        return {
            "iteration_id": iteration.id,
            "iteration_num": iteration_num,
            "image_b64": f"data:image/png;base64,{image_b64}",
            "prompt_used": image_prompt,
            "critique": {
                "match_scores": critique_result.match_scores,
                "preserved_traits": critique_result.preserved_traits,
                "lost_traits": critique_result.lost_traits,
                "interesting_mutations": critique_result.interesting_mutations,
            },
            "updated_profile": critique_result.updated_style_profile.model_dump(),
        }

    except Exception as e:
        error_msg = str(e)
        error_tb = traceback.format_exc()
        logger.error(f"Iteration failed: {error_msg}\n{error_tb}")

        await log(f"ERROR: {error_msg}", "error", "iterate")
        await log(f"Stack trace: {error_tb[-500:]}", "error", "iterate")
        await manager.broadcast_error(session_id, error_msg)

        session.status = SessionStatus.ERROR.value
        await db.commit()
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/feedback")
async def submit_feedback(
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit user feedback for an iteration."""
    result = await db.execute(
        select(Iteration).where(Iteration.id == data.iteration_id)
    )
    iteration = result.scalar_one_or_none()

    if not iteration:
        raise HTTPException(status_code=404, detail="Iteration not found")

    iteration.approved = data.approved
    iteration.feedback = data.notes
    await db.commit()

    return {
        "status": "feedback_recorded",
        "iteration_id": iteration.id,
        "approved": iteration.approved,
    }


@router.post("/apply-update")
async def apply_profile_update(
    session_id: str,
    updated_profile: StyleProfile,
    db: AsyncSession = Depends(get_db),
):
    """Apply an updated style profile from critique."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    current_version = max(
        (sp.version for sp in session.style_profiles), default=0
    )
    new_version = current_version + 1

    new_profile_db = StyleProfileDB(
        session_id=session_id,
        version=new_version,
        profile_json=updated_profile.model_dump(),
    )
    db.add(new_profile_db)
    await db.commit()

    return {"version": new_version, "profile": updated_profile.model_dump()}


@router.post("/auto")
async def run_auto_mode(
    data: AutoModeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run multiple iterations automatically until target score or max iterations."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        raise HTTPException(status_code=400, detail="No style profile found")

    if not session.original_image_path:
        raise HTTPException(status_code=400, detail="No original image found")

    results = []

    for i in range(data.max_iterations):
        # Refresh session data
        await db.refresh(session)
        result = await db.execute(
            select(Session)
            .options(
                selectinload(Session.style_profiles),
                selectinload(Session.iterations),
            )
            .where(Session.id == data.session_id)
        )
        session = result.scalar_one()

        # Get latest style profile
        latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
        style_profile = StyleProfile(**latest_profile_db.profile_json)

        # Gather rich feedback history with approval status and critique data
        feedback_history = []
        for it in session.iterations:
            if it.approved is not None or it.feedback:
                entry = {
                    "iteration": it.iteration_num,
                    "approved": it.approved,
                    "notes": it.feedback,
                }
                if it.critique_json:
                    entry["preserved_traits"] = it.critique_json.get("preserved_traits", [])
                    entry["lost_traits"] = it.critique_json.get("lost_traits", [])
                feedback_history.append(entry)

        try:
            # Generate
            session.status = SessionStatus.GENERATING.value
            await db.commit()

            image_prompt = await style_agent.generate_image_prompt(
                style_profile=style_profile,
                subject=data.subject,
                feedback_history=feedback_history,
            )

            image_b64 = await comfyui_service.generate(prompt=image_prompt)

            iteration_num = len(session.iterations) + 1
            filename = storage_service.get_iteration_filename(iteration_num)
            image_path = await storage_service.save_image(
                session.id, image_b64, filename
            )

            iteration = Iteration(
                session_id=session.id,
                iteration_num=iteration_num,
                image_path=str(image_path),
                prompt_used=image_prompt,
            )
            db.add(iteration)
            await db.flush()

            # Critique
            session.status = SessionStatus.CRITIQUING.value
            await db.commit()

            original_b64 = await storage_service.load_image_raw(
                session.original_image_path
            )
            critique_result = await style_critic.critique(
                original_image_b64=original_b64,
                generated_image_b64=image_b64,
                style_profile=style_profile,
                creativity_level=data.creativity_level,
            )

            iteration.scores_json = critique_result.match_scores
            iteration.critique_json = {
                "preserved_traits": critique_result.preserved_traits,
                "lost_traits": critique_result.lost_traits,
                "interesting_mutations": critique_result.interesting_mutations,
            }
            iteration.approved = True  # Auto-approved in auto mode

            # Apply updated profile
            new_version = latest_profile_db.version + 1
            new_profile_db = StyleProfileDB(
                session_id=session.id,
                version=new_version,
                profile_json=critique_result.updated_style_profile.model_dump(),
            )
            db.add(new_profile_db)

            await db.commit()
            await db.refresh(iteration)

            overall_score = critique_result.match_scores.get("overall", 0)

            results.append({
                "iteration_num": iteration_num,
                "overall_score": overall_score,
                "prompt_used": image_prompt,
            })

            # Check if we've reached target score
            if overall_score >= data.target_score:
                session.status = SessionStatus.COMPLETED.value
                await db.commit()
                break

        except Exception as e:
            session.status = SessionStatus.ERROR.value
            await db.commit()
            results.append({
                "iteration_num": i + 1,
                "error": str(e),
            })
            break

    session.status = SessionStatus.READY.value
    await db.commit()

    return {
        "iterations_run": len(results),
        "results": results,
        "final_score": results[-1].get("overall_score") if results else None,
    }


@router.post("/auto-improve")
async def run_auto_improve(
    data: AutoImproveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run intelligent auto-iteration that focuses on improving weak dimensions.
    Analyzes each iteration's scores and adjusts focus to address weaknesses.
    """
    session_id = data.session_id

    async def log(msg: str, level: str = "info", step: str = "auto-improve"):
        logger.info(f"[{step}] {msg}")
        await manager.broadcast_log(session_id, msg, level, step)

    logger.info(f"=== AUTO-IMPROVE ENDPOINT CALLED === Session: {session_id}")
    await log(f"Starting Auto-Improve mode (target: {data.target_score}, max: {data.max_iterations})", "info")

    # Get session with all related data
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles), selectinload(Session.iterations))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        await log("Session not found", "error")
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.style_profiles:
        await log("No style profile found - extract style first", "error")
        raise HTTPException(status_code=400, detail="No style profile found")

    if not session.original_image_path:
        await log("No original image found", "error")
        raise HTTPException(status_code=400, detail="No original image found")

    # Initialize debug log file - write header immediately
    debug_log_path = storage_service.get_session_dir(session.id) / "auto_improve_debug.txt"

    async def write_debug(content: str, mode: str = 'a'):
        """Helper to write debug info incrementally"""
        try:
            import aiofiles
            async with aiofiles.open(debug_log_path, mode) as f:
                await f.write(content + '\n')
        except Exception as e:
            logger.error(f"Failed to write debug log: {e}")

    # Write header immediately
    header = []
    header.append("=" * 80)
    header.append(f"AUTO-IMPROVE DEBUG LOG")
    header.append(f"Session: {session.id} - {session.name}")
    header.append(f"Subject: {data.subject}")
    header.append(f"Target Score: {data.target_score}, Max Iterations: {data.max_iterations}")
    header.append(f"Started: {datetime.utcnow().isoformat()}")
    header.append("=" * 80)
    header.append("")

    await write_debug('\n'.join(header), mode='w')  # Overwrite existing file

    # Load original image once
    original_b64 = await storage_service.load_image_raw(session.original_image_path)

    # Get original extracted style profile (version 1)
    original_profile_db = min(session.style_profiles, key=lambda sp: sp.version)
    original_profile = StyleProfile(**original_profile_db.profile_json)

    # Include original extraction in debug log
    extraction_info = []
    extraction_info.append("\n" + "=" * 80)
    extraction_info.append("ORIGINAL STYLE EXTRACTION")
    extraction_info.append("=" * 80)
    extraction_info.append(f"\nOriginal Style Profile (v{original_profile_db.version}):")
    extraction_info.append(f"Style Name: {original_profile.style_name}")
    extraction_info.append(f"\nCore Invariants ({len(original_profile.core_invariants)}):")
    for inv in original_profile.core_invariants:
        extraction_info.append(f"  - {inv}")
    extraction_info.append(f"\nPalette:")
    extraction_info.append(f"  Saturation: {original_profile.palette.saturation}")
    extraction_info.append(f"  Colors:")
    for color in original_profile.palette.color_descriptions:
        extraction_info.append(f"    - {color}")
    extraction_info.append(f"\nLighting:")
    extraction_info.append(f"  Type: {original_profile.lighting.lighting_type}")
    extraction_info.append(f"  Shadows: {original_profile.lighting.shadows}")
    extraction_info.append(f"  Highlights: {original_profile.lighting.highlights}")
    extraction_info.append(f"\nTexture:")
    extraction_info.append(f"  Surface: {original_profile.texture.surface}")
    extraction_info.append(f"  Noise Level: {original_profile.texture.noise_level}")
    extraction_info.append(f"  Special Effects: {', '.join(original_profile.texture.special_effects) if original_profile.texture.special_effects else 'none'}")
    extraction_info.append(f"\nComposition:")
    extraction_info.append(f"  Camera: {original_profile.composition.camera}")
    extraction_info.append(f"  Framing: {original_profile.composition.framing}")
    extraction_info.append(f"  Depth: {getattr(original_profile.composition, 'depth', 'not extracted')}")
    if hasattr(original_profile.composition, 'structural_notes') and original_profile.composition.structural_notes:
        extraction_info.append(f"  Structural Notes: {original_profile.composition.structural_notes}")
    extraction_info.append(f"\nLine & Shape:")
    extraction_info.append(f"  Line Quality: {original_profile.line_and_shape.line_quality}")
    extraction_info.append(f"  Shape Language: {original_profile.line_and_shape.shape_language}")
    extraction_info.append(f"\nMotifs:")
    extraction_info.append(f"  Recurring Elements: {', '.join(original_profile.motifs.recurring_elements) if original_profile.motifs.recurring_elements else 'none'}")
    extraction_info.append(f"  Forbidden Elements: {', '.join(original_profile.motifs.forbidden_elements) if original_profile.motifs.forbidden_elements else 'none'}")

    await write_debug('\n'.join(extraction_info))

    # Include system prompts
    from pathlib import Path
    prompts_dir = Path(__file__).parent.parent / "prompts"

    prompt_info = []
    prompt_info.append("\n" + "=" * 80)
    prompt_info.append("SYSTEM PROMPTS")
    prompt_info.append("=" * 80)

    # Extractor prompt
    try:
        extractor_prompt = (prompts_dir / "extractor.md").read_text()
        prompt_info.append(f"\n--- Extractor Prompt ({len(extractor_prompt)} chars) ---")
        prompt_info.append(extractor_prompt)
    except Exception as e:
        prompt_info.append(f"\n--- Extractor Prompt: ERROR reading file - {e} ---")

    # Generator prompt
    try:
        generator_prompt = (prompts_dir / "generator.md").read_text()
        prompt_info.append(f"\n--- Style Agent Generator Prompt ({len(generator_prompt)} chars) ---")
        prompt_info.append(generator_prompt)
    except Exception as e:
        prompt_info.append(f"\n--- Generator Prompt: ERROR reading file - {e} ---")

    # Critic prompt
    try:
        critic_prompt = (prompts_dir / "critic.md").read_text()
        prompt_info.append(f"\n--- Critic Prompt ({len(critic_prompt)} chars) ---")
        prompt_info.append(critic_prompt)
    except Exception as e:
        prompt_info.append(f"\n--- Critic Prompt: ERROR reading file - {e} ---")

    await write_debug('\n'.join(prompt_info))

    # Compute training insights from existing iterations
    training_insights = auto_improver.compute_training_insights(session.iterations)

    insights = []
    insights.append("\n" + "=" * 80)
    insights.append("TRAINING CONTEXT")
    insights.append("=" * 80)
    if training_insights.get("historical_best"):
        await log(f"Historical best score: {training_insights['historical_best']:.1f}", "info", "insights")
        insights.append(f"\nHistorical Best Score: {training_insights['historical_best']:.1f}")
    if training_insights.get("dimension_averages"):
        insights.append(f"Dimension Averages: {', '.join([f'{k}={v:.1f}' for k, v in training_insights['dimension_averages'].items() if k != 'overall'])}")
    if training_insights.get("frequently_lost_traits"):
        await log(f"Frequently lost traits: {', '.join(training_insights['frequently_lost_traits'][:3])}", "warning", "insights")
        insights.append(f"Frequently Lost Traits: {', '.join(training_insights['frequently_lost_traits'][:5])}")

    insights.append(f"\nPrevious Iterations: {len(session.iterations)}")
    insights.append(f"Latest Style Profile Version: {max((sp.version for sp in session.style_profiles), default=0)}")
    insights.append("")

    await write_debug('\n'.join(insights))

    results = []
    baseline_scores = None  # Track scores from current iteration for weak dimension detection
    best_approved_score = None  # Track best approved overall score for incremental improvement
    previous_corrections = None  # Track corrections from previous iteration for vectorized feedback
    approved_count = 0
    rejected_count = 0

    for i in range(data.max_iterations):
        iteration_num = i + 1
        await log(f"=== Iteration {iteration_num}/{data.max_iterations} ===", "info", "iteration")
        await manager.broadcast_progress(session_id, "auto-improve", int((i / data.max_iterations) * 100), f"Iteration {iteration_num}")

        # Check if user requested stop
        if _stop_requests.get(session_id, False):
            await log(f"Training stopped by user at iteration {iteration_num}", "warning", "stop")
            await write_debug(f"\n{'='*60}\nTRAINING STOPPED BY USER at iteration {iteration_num}\n{'='*60}\n")
            _stop_requests.pop(session_id, None)  # Clear the flag
            session.status = SessionStatus.READY.value
            await db.commit()
            return {
                "iterations_run": len(results),
                "results": results,
                "final_score": results[-1].get("overall_score") if results else None,
                "stopped_by_user": True,
                "message": f"Training stopped by user at iteration {iteration_num}",
            }

        # Refresh session data
        await db.refresh(session)
        result = await db.execute(
            select(Session)
            .options(
                selectinload(Session.style_profiles),
                selectinload(Session.iterations),
            )
            .where(Session.id == data.session_id)
        )
        session = result.scalar_one()

        # Get latest style profile
        latest_profile_db = max(session.style_profiles, key=lambda sp: sp.version)
        style_profile = StyleProfile(**latest_profile_db.profile_json)

        # Gather feedback history (only from approved iterations)
        feedback_history = []
        for it in session.iterations:
            if it.approved:  # Only use approved iterations for feedback
                entry = {
                    "iteration": it.iteration_num,
                    "approved": it.approved,
                    "notes": it.feedback or "Auto-approved",
                }
                if it.critique_json:
                    entry["preserved_traits"] = it.critique_json.get("preserved_traits", [])
                    entry["lost_traits"] = it.critique_json.get("lost_traits", [])
                feedback_history.append(entry)

        try:
            # Run focused iteration
            session.status = SessionStatus.GENERATING.value
            await db.commit()

            iteration_result = await auto_improver.run_focused_iteration(
                session_id=session_id,
                subject=data.subject,
                style_profile=style_profile,
                original_image_b64=original_b64,
                feedback_history=feedback_history,
                previous_scores=baseline_scores,  # Use for weak dimension detection
                previous_corrections=previous_corrections,  # Vectorized feedback from previous iteration
                creativity_level=data.creativity_level,
                training_insights=training_insights,  # Use for threshold adaptation and lost traits
                log_fn=log,
            )

            # Evaluate iteration: should it be approved or rejected?
            new_scores = iteration_result["critique"].match_scores
            should_approve, eval_reason, eval_analysis = auto_improver.evaluate_iteration(
                new_scores=new_scores,
                critique_result=iteration_result["critique"],
                style_profile=style_profile,  # For checking original_subject
                best_approved_score=best_approved_score,
                training_insights=training_insights,
                previous_scores=baseline_scores,  # For weighted delta calculation
            )

            # Extract corrections for next iteration (always update, even from rejected iterations)
            # Corrections from rejected iterations are especially important for recovery
            try:
                critique_result = iteration_result["critique"]
                if hasattr(critique_result, 'corrections') and critique_result.corrections:
                    # Convert Pydantic models to dicts for easy passing
                    previous_corrections = []
                    for corr in critique_result.corrections:
                        try:
                            if hasattr(corr, 'model_dump'):
                                previous_corrections.append(corr.model_dump())
                            elif isinstance(corr, dict):
                                previous_corrections.append(corr)
                            else:
                                await log(f"Skipping invalid correction type: {type(corr)}", "warning", "corrections")
                        except Exception as e:
                            await log(f"Failed to convert correction: {e}", "warning", "corrections")

                    if previous_corrections:
                        await log(f"Extracted {len(previous_corrections)} corrections for next iteration", "info", "corrections")
                    else:
                        await log("No valid corrections could be extracted", "warning", "corrections")
                        previous_corrections = None
                else:
                    await log("No corrections in critique result (VLM may not have provided them)", "warning", "corrections")
                    previous_corrections = None
            except Exception as e:
                await log(f"Error extracting corrections: {e}", "error", "corrections")
                previous_corrections = None  # Continue without corrections if extraction fails

            # DEBUG: Log comprehensive VLM metadata and decision analysis (to console AND file)
            iter_debug = []
            iter_debug.append(f"\n{'='*60}")
            iter_debug.append(f"ITERATION {iteration_num}")
            iter_debug.append(f"{'='*60}")

            # Feedback history context
            approved_count_history = sum(1 for fb in feedback_history if fb.get("approved"))
            rejected_count_history = sum(1 for fb in feedback_history if not fb.get("approved"))
            iter_debug.append(f"\nFeedback History: {approved_count_history} approved, {rejected_count_history} rejected iterations")
            if feedback_history:
                recent = feedback_history[-3:]  # Last 3 iterations (approved or rejected)
                iter_debug.append(f"Recent feedback context:")
                for fb in recent:
                    approval = "✓" if fb.get("approved") else "✗"
                    notes = fb.get("notes", "")
                    # Show full notes for recovery guidance, truncated for others
                    if "RECOVERY NEEDED" in notes:
                        iter_debug.append(f"  Iteration {fb['iteration']}: {approval} - {notes}")
                        if fb.get("failure_analysis"):
                            for detail in fb["failure_analysis"][:3]:  # First 3 details
                                iter_debug.append(f"    {detail}")
                    else:
                        iter_debug.append(f"  Iteration {fb['iteration']}: {approval} - {notes[:80]}")

            # Weak dimensions and focus areas
            if iteration_result["weak_dimensions"]:
                iter_debug.append(f"\nWeak Dimensions Targeted: {', '.join(iteration_result['weak_dimensions'])}")
            if iteration_result["focused_areas"]:
                iter_debug.append(f"Focused Areas: {', '.join(iteration_result['focused_areas'])}")

            # Image generation prompt (FULL - not truncated)
            iter_debug.append(f"\n--- Image Generation Prompt ({len(iteration_result['prompt_used'])} chars) ---")
            iter_debug.append(iteration_result['prompt_used'])

            # VLM Critique Analysis
            iter_debug.append(f"\n--- VLM Critique Analysis ---")
            iter_debug.append(f"Overall Score: {new_scores.get('overall', 0)}")
            iter_debug.append(f"Dimension Scores: {', '.join([f'{k}={v}' for k, v in new_scores.items() if k != 'overall'])}")

            if iteration_result["critique"].preserved_traits:
                iter_debug.append(f"\n✓ Preserved Traits ({len(iteration_result['critique'].preserved_traits)}):")
                for trait in iteration_result["critique"].preserved_traits[:10]:
                    iter_debug.append(f"  - {trait}")
                if len(iteration_result["critique"].preserved_traits) > 10:
                    iter_debug.append(f"  ... and {len(iteration_result['critique'].preserved_traits) - 10} more")

            if iteration_result["critique"].lost_traits:
                iter_debug.append(f"\n✗ Lost Traits ({len(iteration_result['critique'].lost_traits)}):")
                for trait in iteration_result["critique"].lost_traits:
                    iter_debug.append(f"  - {trait}")

            if iteration_result["critique"].interesting_mutations:
                iter_debug.append(f"\n~ Interesting Mutations ({len(iteration_result['critique'].interesting_mutations)}):")
                for mutation in iteration_result["critique"].interesting_mutations[:5]:
                    iter_debug.append(f"  - {mutation}")

            await log(f"[DEBUG] Overall Score: {new_scores.get('overall', 0)}", "info", "debug")
            await log(f"[DEBUG] Dimension Scores: {', '.join([f'{k}={v}' for k, v in new_scores.items() if k != 'overall'])}", "info", "debug")

            # DEBUG: Log weighted dimension deltas
            if eval_analysis.get("dimension_deltas"):
                dimension_changes = []
                for d, delta in eval_analysis["dimension_deltas"].items():
                    if abs(delta) > 2:  # Only show significant changes
                        weight = eval_analysis.get("weighted_deltas", {}).get(d, 0)
                        dimension_changes.append(f"{d}({delta:+.0f}, w={weight:+.1f})")
                if dimension_changes:
                    iter_debug.append(f"Dimension Deltas: {', '.join(dimension_changes)}")
                    await log(f"[DEBUG] Dimension Deltas: {', '.join(dimension_changes)}", "info", "debug")

            # DEBUG: Log weighted net progress
            if "weighted_net_progress" in eval_analysis:
                wnp = eval_analysis["weighted_net_progress"]
                iter_debug.append(f"Weighted Net Progress: {wnp:+.1f} (threshold: strong≥3.0, weak≥1.0)")
                await log(f"[DEBUG] Weighted Net Progress: {wnp:+.1f}", "info", "debug")

            # DEBUG: Log vs best approved
            if eval_analysis.get("best_approved_score"):
                vs_best = f"vs Best Approved: {eval_analysis.get('improvement', 0):+.0f} ({eval_analysis['best_approved_score']} → {new_scores.get('overall', 0)})"
                iter_debug.append(vs_best)
                await log(f"[DEBUG] {vs_best}", "info", "debug")

            # DEBUG: Log approval decision details
            iter_debug.append(f"\n--- Decision Analysis ---")
            iter_debug.append(f"  - Meets targets (Tier 1): {eval_analysis.get('meets_targets', False)}")
            iter_debug.append(f"  - Strong weighted progress (Tier 2): {eval_analysis.get('strong_weighted_progress', False)} (≥3.0)")
            iter_debug.append(f"  - Weak positive progress (Tier 3): {eval_analysis.get('weak_positive_progress', False)} (≥1.0)")
            iter_debug.append(f"  - First iteration: {best_approved_score is None}")

            await log(f"[DEBUG] Decision Analysis:", "info", "debug")
            await log(f"  - Meets targets (Tier 1): {eval_analysis.get('meets_targets', False)}", "info", "debug")
            await log(f"  - Strong weighted progress (Tier 2): {eval_analysis.get('strong_weighted_progress', False)}", "info", "debug")
            await log(f"  - Weak positive progress (Tier 3): {eval_analysis.get('weak_positive_progress', False)}", "info", "debug")
            await log(f"  - First iteration: {best_approved_score is None}", "info", "debug")

            # Log catastrophic failures with categorization
            if eval_analysis.get('structural_catastrophic'):
                struct_msg = f"  - Structural catastrophic: {eval_analysis['structural_catastrophic']} (INSTANT REJECT)"
                iter_debug.append(struct_msg)
                await log(struct_msg, "error", "debug")
            if eval_analysis.get('technique_catastrophic'):
                tech_msg = f"  - Technique catastrophic: {eval_analysis['technique_catastrophic']} (check net progress)"
                iter_debug.append(tech_msg)
                await log(tech_msg, "warning", "debug")
            if eval_analysis.get('stylistic_catastrophic'):
                style_msg = f"  - Stylistic catastrophic: {eval_analysis['stylistic_catastrophic']} (gated by net progress)"
                iter_debug.append(style_msg)
                await log(style_msg, "warning", "debug")
            if eval_analysis.get('subject_drift_failures'):
                drift_msg = f"  - Subject drift detected: {eval_analysis['subject_drift_failures'][:1]}"
                iter_debug.append(drift_msg)
                await log(drift_msg, "error", "debug")

            # Log evaluation
            decision_status = "✓ APPROVED" if should_approve else "✗ REJECTED"
            iter_debug.append(f"\n{decision_status}: {eval_reason}")

            # If rejected, note that recovery guidance will be generated
            if not should_approve:
                iter_debug.append(f"\n⚠ REJECTION HANDLING:")
                iter_debug.append(f"  - Style profile will revert to v{latest_profile_db.version} (last approved)")
                iter_debug.append(f"  - Baseline scores will NOT update (keeping last approved state)")
                iter_debug.append(f"  - Recovery guidance will be added to next iteration's feedback")

            # DEBUG: Log current style profile being used
            iter_debug.append(f"\n--- Style Profile (v{latest_profile_db.version}) ---")
            iter_debug.append(f"Style Name: {style_profile.style_name}")
            iter_debug.append(f"Core Invariants: {', '.join(style_profile.core_invariants[:5])}")
            iter_debug.append(f"Palette: {', '.join(style_profile.palette.color_descriptions[:3])} (saturation: {style_profile.palette.saturation})")
            iter_debug.append(f"Lighting: {style_profile.lighting.lighting_type}, shadows: {style_profile.lighting.shadows}")
            iter_debug.append(f"Texture: {style_profile.texture.surface}, noise: {style_profile.texture.noise_level}")
            iter_debug.append(f"Composition: {style_profile.composition.camera}, {style_profile.composition.framing}")
            iter_debug.append(f"Line Quality: {style_profile.line_and_shape.line_quality}")

            # DEBUG: Log VLM's updated style profile suggestions
            if iteration_result["critique"].updated_style_profile:
                updated = iteration_result["critique"].updated_style_profile
                iter_debug.append(f"\n--- VLM Updated Style Profile (suggested changes) ---")
                # Check for changes in key areas
                if updated.palette.color_descriptions != style_profile.palette.color_descriptions:
                    iter_debug.append(f"Palette change: {', '.join(updated.palette.color_descriptions[:3])}")
                if updated.lighting.lighting_type != style_profile.lighting.lighting_type:
                    iter_debug.append(f"Lighting change: {updated.lighting.lighting_type}")
                if updated.texture.surface != style_profile.texture.surface:
                    iter_debug.append(f"Texture change: {updated.texture.surface}")
                if updated.composition.camera != style_profile.composition.camera:
                    iter_debug.append(f"Composition change: {updated.composition.camera}")
                if updated.line_and_shape.line_quality != style_profile.line_and_shape.line_quality:
                    iter_debug.append(f"Line quality change: {updated.line_and_shape.line_quality}")

            # Write this iteration's debug info to file immediately
            await write_debug('\n'.join(iter_debug))

            if should_approve:
                await log(f"✓ {eval_reason}", "success", "evaluation")
                approved_count += 1
            else:
                await log(f"✗ {eval_reason}", "warning", "evaluation")
                rejected_count += 1

            # Save iteration
            iteration_num_db = len(session.iterations) + 1
            filename = storage_service.get_iteration_filename(iteration_num_db)
            image_path = await storage_service.save_image(
                session.id, iteration_result["image_b64"], filename
            )

            # Build detailed feedback message with debug info
            feedback_parts = [eval_reason]

            # Add score details
            feedback_parts.append(f"\nScores: Overall={new_scores.get('overall', 0)}")
            dimension_scores = [f"{k}={v}" for k, v in new_scores.items() if k != 'overall']
            feedback_parts.append(f"Dimensions: {', '.join(dimension_scores)}")

            # Add weighted dimension changes
            if eval_analysis.get("dimension_deltas"):
                changed = [f"{d}({delta:+.0f})" for d, delta in eval_analysis["dimension_deltas"].items() if abs(delta) > 2]
                if changed:
                    feedback_parts.append(f"Dimension Δ: {', '.join(changed)}")

            if eval_analysis.get("weighted_net_progress") is not None:
                wnp = eval_analysis["weighted_net_progress"]
                feedback_parts.append(f"Weighted Net Progress: {wnp:+.1f}")

            if eval_analysis.get("best_approved_score"):
                feedback_parts.append(f"vs Best approved: {eval_analysis.get('improvement', 0):+.0f} ({eval_analysis['best_approved_score']} → {new_scores.get('overall', 0)})")

            # Add approval tier breakdown
            tiers = []
            if eval_analysis.get('meets_targets'): tiers.append("Tier 1 (quality)")
            if eval_analysis.get('strong_weighted_progress'): tiers.append("Tier 2 (strong Δ)")
            if eval_analysis.get('weak_positive_progress'): tiers.append("Tier 3 (weak +Δ)")
            if best_approved_score is None: tiers.append("First iteration")
            feedback_parts.append(f"Checked: {', '.join(tiers) if tiers else 'None passed'}")

            feedback_msg = "\n".join(feedback_parts)

            iteration = Iteration(
                session_id=session.id,
                iteration_num=iteration_num_db,
                image_path=str(image_path),
                prompt_used=iteration_result["prompt_used"],
                scores_json=new_scores,
                critique_json={
                    "preserved_traits": iteration_result["critique"].preserved_traits,
                    "lost_traits": iteration_result["critique"].lost_traits,
                    "interesting_mutations": iteration_result["critique"].interesting_mutations,
                },
                approved=should_approve,
                feedback=feedback_msg,
            )
            db.add(iteration)
            await db.flush()

            # Only apply updated profile if approved
            if should_approve:
                new_version = latest_profile_db.version + 1
                new_profile_db = StyleProfileDB(
                    session_id=session.id,
                    version=new_version,
                    profile_json=iteration_result["critique"].updated_style_profile.model_dump(),
                )
                db.add(new_profile_db)
                await log(f"Profile updated to v{new_version}", "success", "update")

                # Update best approved score
                overall_score = new_scores.get("overall", 0)
                if best_approved_score is None or overall_score > best_approved_score:
                    best_approved_score = overall_score
                    await log(f"New best approved score: {best_approved_score}", "success", "milestone")

                # Update baseline_scores only from approved iterations
                baseline_scores = new_scores
                await log("Baseline scores updated from approved iteration", "success", "update")
            else:
                await log("Profile not updated (iteration rejected)", "info", "update")
                await log("Baseline scores NOT updated (keeping last approved state)", "info", "update")

                # CRITICAL: Add recovery guidance to feedback history for next iteration
                # Build specific recovery instructions based on what failed
                recovery_guidance = {
                    "iteration": iteration_num_db,
                    "approved": False,
                    "notes": f"RECOVERY NEEDED: Previous iteration REJECTED. {eval_reason}",
                }

                # Add specific failure analysis
                failure_details = []

                # Catastrophic failures
                if eval_analysis.get('catastrophic_failures'):
                    cat_failures = eval_analysis['catastrophic_failures']
                    failure_details.append(f"CATASTROPHIC: {', '.join(cat_failures)}")
                    for failure in cat_failures:
                        dim = failure.split('=')[0]
                        failure_details.append(f"  → {dim}: Must restore from last approved iteration")

                # Subject drift
                if eval_analysis.get('subject_drift_failures'):
                    drift = eval_analysis['subject_drift_failures']
                    failure_details.append(f"SUBJECT DRIFT: {', '.join(drift[:2])}")
                    failure_details.append(f"  → Restore subject/composition from original")

                # Lost traits
                if iteration_result["critique"].lost_traits:
                    lost = iteration_result["critique"].lost_traits[:3]
                    failure_details.append(f"LOST TRAITS: {', '.join(lost)}")
                    failure_details.append(f"  → These must be restored in next iteration")

                # What to avoid (interesting mutations that broke things)
                if iteration_result["critique"].interesting_mutations:
                    mutations = iteration_result["critique"].interesting_mutations[:2]
                    failure_details.append(f"AVOID: {', '.join(mutations)}")
                    failure_details.append(f"  → These introduced incompatible elements")

                recovery_guidance["failure_analysis"] = failure_details
                recovery_guidance["action"] = "Revert to last approved state and correct the specific failures listed above"

                # Add to feedback history so next iteration knows what to fix
                feedback_history.append(recovery_guidance)

                await log(f"Recovery guidance added: {len(failure_details)} specific issues identified", "warning", "recovery")

                # Log recovery guidance to debug file
                recovery_debug = []
                recovery_debug.append(f"\n--- RECOVERY GUIDANCE GENERATED ---")
                recovery_debug.append(f"Action: {recovery_guidance['action']}")
                recovery_debug.append(f"\nFailure Analysis ({len(failure_details)} issues):")
                for detail in failure_details:
                    recovery_debug.append(f"  {detail}")
                recovery_debug.append(f"\nThis guidance will be included in the next iteration's feedback history.")
                await write_debug('\n'.join(recovery_debug))

            await db.commit()
            await db.refresh(iteration)

            # Store results
            overall_score = new_scores.get("overall", 0)

            results.append({
                "iteration_num": iteration_num_db,
                "overall_score": overall_score,
                "weak_dimensions": iteration_result["weak_dimensions"],
                "focused_areas": iteration_result["focused_areas"],
                "scores": new_scores,
                "approved": should_approve,
                "eval_reason": eval_reason,
            })

            # Check stopping conditions (only consider approved iterations)
            if should_approve:
                # Check if we've reached target with this approved iteration
                should_continue, reason = auto_improver.should_continue(
                    current_score=overall_score,
                    target_score=data.target_score,
                    iteration=iteration_num,
                    max_iterations=data.max_iterations,
                )

                await log(reason, "success" if not should_continue else "info", "decision")

                if not should_continue:
                    session.status = SessionStatus.COMPLETED.value
                    await db.commit()
                    break
            else:
                # Rejected iteration - continue trying
                await log(f"Continuing (iteration rejected, need improvement)", "info", "decision")

        except Exception as e:
            error_msg = str(e)
            error_tb = traceback.format_exc()
            logger.error(f"Auto-improve iteration failed: {error_msg}\n{error_tb}")

            await log(f"ERROR: {error_msg}", "error")
            await manager.broadcast_error(session_id, error_msg)

            session.status = SessionStatus.ERROR.value
            await db.commit()

            results.append({
                "iteration_num": iteration_num,
                "error": error_msg,
            })
            break

    session.status = SessionStatus.READY.value
    await db.commit()

    # Find best approved iteration
    approved_results = [r for r in results if r.get("approved")]
    best_score = max([r["overall_score"] for r in approved_results]) if approved_results else None

    await log(
        f"Auto-Improve complete! {len(results)} iterations ({approved_count} approved, {rejected_count} rejected)",
        "success"
    )
    await log(f"Best score achieved: {best_score if best_score else 'N/A'}", "success")

    # DEBUG: Log score progression summary
    await log("=== SCORE PROGRESSION SUMMARY ===", "info", "summary")

    summary = []
    summary.append("\n" + "=" * 80)
    summary.append("SCORE PROGRESSION SUMMARY")
    summary.append("=" * 80)

    for idx, result in enumerate(results, 1):
        status = "✓ APPROVED" if result.get("approved") else "✗ REJECTED"
        overall = result.get("overall_score", "N/A")
        await log(f"Iteration {idx}: Overall {overall} - {status}", "info", "summary")
        summary.append(f"\nIteration {idx}: Overall {overall} - {status}")

        if result.get("scores"):
            dim_str = ", ".join([f"{k}={v}" for k, v in result["scores"].items() if k != "overall"])
            await log(f"  Dimensions: {dim_str}", "info", "summary")
            summary.append(f"  Dimensions: {dim_str}")
        if result.get("eval_reason"):
            await log(f"  Reason: {result['eval_reason']}", "info", "summary")
            summary.append(f"  Reason: {result['eval_reason']}")

    # Write final summary to debug log
    summary.append("\n" + "=" * 80)
    summary.append(f"Completed: {datetime.utcnow().isoformat()}")
    summary.append(f"Total: {len(results)} iterations ({approved_count} approved, {rejected_count} rejected)")
    summary.append(f"Best score: {best_score if best_score else 'N/A'}")
    summary.append(f"Target reached: {(best_score >= data.target_score) if best_score else False}")
    summary.append("=" * 80)

    await write_debug('\n'.join(summary))
    await log(f"Debug log written to: {debug_log_path}", "success", "debug")
    logger.info(f"DEBUG LOG WRITTEN TO: {debug_log_path}")

    await manager.broadcast_progress(session_id, "complete", 100, "Auto-Improve complete")
    await manager.broadcast_complete(session_id)

    return {
        "iterations_run": len(results),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "results": results,
        "final_score": results[-1].get("overall_score") if results else None,
        "best_score": best_score,
        "target_reached": (best_score >= data.target_score) if best_score else False,
    }


@router.post("/stop")
async def stop_auto_improve(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Request graceful stop of auto-improve loop for a session.
    The loop will finish the current iteration and exit cleanly.
    """
    # Verify session exists
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Set stop flag
    _stop_requests[session_id] = True

    logger.info(f"Stop requested for session {session_id}")
    await manager.broadcast_log(
        session_id,
        "Stop requested - training will halt after current iteration completes",
        "warning",
        "stop"
    )

    return {
        "session_id": session_id,
        "message": "Stop requested - training will halt after current iteration completes",
    }
