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

    # Compute training insights from existing iterations
    training_insights = auto_improver.compute_training_insights(session.iterations)

    insights = []
    if training_insights.get("historical_best"):
        await log(f"Historical best score: {training_insights['historical_best']:.1f}", "info", "insights")
        insights.append(f"\n--- Training Insights ---")
        insights.append(f"Historical Best Score: {training_insights['historical_best']:.1f}")
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
    approved_count = 0
    rejected_count = 0

    for i in range(data.max_iterations):
        iteration_num = i + 1
        await log(f"=== Iteration {iteration_num}/{data.max_iterations} ===", "info", "iteration")
        await manager.broadcast_progress(session_id, "auto-improve", int((i / data.max_iterations) * 100), f"Iteration {iteration_num}")

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
            )

            # DEBUG: Log comprehensive VLM metadata and decision analysis (to console AND file)
            iter_debug = []
            iter_debug.append(f"\n{'='*60}")
            iter_debug.append(f"ITERATION {iteration_num}")
            iter_debug.append(f"{'='*60}")

            # Feedback history context
            iter_debug.append(f"\nFeedback History: {len(feedback_history)} approved iterations")
            if feedback_history:
                recent = feedback_history[-3:]  # Last 3 approved iterations
                iter_debug.append(f"Recent feedback context:")
                for fb in recent:
                    approval = "✓" if fb.get("approved") else "✗"
                    notes = fb.get("notes", "")[:50]
                    iter_debug.append(f"  Iteration {fb['iteration']}: {approval} - {notes}")

            # Weak dimensions and focus areas
            if iteration_result["weak_dimensions"]:
                iter_debug.append(f"\nWeak Dimensions Targeted: {', '.join(iteration_result['weak_dimensions'])}")
            if iteration_result["focused_areas"]:
                iter_debug.append(f"Focused Areas: {', '.join(iteration_result['focused_areas'])}")

            # Image generation prompt
            iter_debug.append(f"\n--- Image Generation Prompt ({len(iteration_result['prompt_used'])} chars) ---")
            iter_debug.append(iteration_result['prompt_used'][:500] + ("..." if len(iteration_result['prompt_used']) > 500 else ""))

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

            # DEBUG: Log dimension changes vs historical average
            if eval_analysis.get("dimension_improvements"):
                improved = [f"{d}({'+' if delta > 0 else ''}{delta:.0f})" for d, delta in eval_analysis["dimension_improvements"].items() if abs(delta) > 2]
                if improved:
                    iter_debug.append(f"Dimension Changes vs History: {', '.join(improved)}")
                    await log(f"[DEBUG] Dimension Changes vs History: {', '.join(improved)}", "info", "debug")

            # DEBUG: Log vs best approved
            if eval_analysis.get("best_approved_score"):
                vs_best = f"vs Best Approved: {eval_analysis.get('improvement', 0):+.0f} ({eval_analysis['best_approved_score']} → {new_scores.get('overall', 0)})"
                iter_debug.append(vs_best)
                await log(f"[DEBUG] {vs_best}", "info", "debug")

            # DEBUG: Log approval decision details
            iter_debug.append(f"\n--- Decision Analysis ---")
            iter_debug.append(f"  - Meets targets (Tier 1): {eval_analysis.get('meets_targets', False)}")
            iter_debug.append(f"  - Incremental improvement (Tier 2): {eval_analysis.get('improves_incrementally', False)} (need +3)")
            iter_debug.append(f"  - Net progress (Tier 2b): {eval_analysis.get('net_progress', False)}")
            iter_debug.append(f"  - First iteration: {best_approved_score is None}")

            await log(f"[DEBUG] Decision Analysis:", "info", "debug")
            await log(f"  - Meets targets (Tier 1): {eval_analysis.get('meets_targets', False)}", "info", "debug")
            await log(f"  - Incremental improvement (Tier 2): {eval_analysis.get('improves_incrementally', False)} (need +3)", "info", "debug")
            await log(f"  - Net progress (Tier 2b): {eval_analysis.get('net_progress', False)}", "info", "debug")
            await log(f"  - First iteration: {best_approved_score is None}", "info", "debug")

            if eval_analysis.get('subject_drift_failures'):
                drift_msg = f"  - Subject drift detected: {eval_analysis['subject_drift_failures'][:1]}"
                iter_debug.append(drift_msg)
                await log(drift_msg, "warning", "debug")
            if eval_analysis.get('catastrophic_failures'):
                cat_msg = f"  - Catastrophic failures: {eval_analysis['catastrophic_failures']}"
                iter_debug.append(cat_msg)
                await log(cat_msg, "error", "debug")

            # Log evaluation
            decision_status = "✓ APPROVED" if should_approve else "✗ REJECTED"
            iter_debug.append(f"\n{decision_status}: {eval_reason}")

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

            # Add decision analysis
            if eval_analysis.get("dimension_improvements"):
                improved = [f"{d}({'+' if delta > 0 else ''}{delta:.0f})" for d, delta in eval_analysis["dimension_improvements"].items() if abs(delta) > 2]
                if improved:
                    feedback_parts.append(f"Changes vs history: {', '.join(improved)}")

            if eval_analysis.get("best_approved_score"):
                feedback_parts.append(f"vs Best approved: {eval_analysis.get('improvement', 0):+.0f} ({eval_analysis['best_approved_score']} → {new_scores.get('overall', 0)})")

            # Add approval tier breakdown
            tiers = []
            if eval_analysis.get('meets_targets'): tiers.append("Tier 1 (targets)")
            if eval_analysis.get('improves_incrementally'): tiers.append("Tier 2 (incremental)")
            if eval_analysis.get('net_progress'): tiers.append("Tier 2b (net progress)")
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
            else:
                await log("Profile not updated (iteration rejected)", "info", "update")

            # Always update baseline_scores for weak dimension detection (regardless of approval)
            baseline_scores = new_scores

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
