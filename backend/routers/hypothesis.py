"""
Hypothesis mode API endpoints.

Provides endpoints for multi-hypothesis style extraction, testing, and selection.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.schemas import SessionStatus, StyleProfile
from backend.models.db_models import Session, StyleProfileDB, HypothesisSetDB
from backend.models.hypothesis_models import (
    HypothesisExtractionRequest,
    HypothesisTestRequest,
    HypothesisExploreRequest,
    HypothesisSelectRequest,
    HypothesisExploreResponse,
    HypothesisSet,
    StyleHypothesis,
)
from backend.services.storage import storage_service
from backend.services.hypothesis_extractor import hypothesis_extractor
from backend.services.hypothesis_tester import hypothesis_tester
from backend.services.hypothesis_selector import hypothesis_selector
from backend.services.vlm import vlm_service
from backend.services.comfyui import comfyui_service
from backend.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hypothesis", tags=["hypothesis"])

# In-memory store for stop requests (session_id -> bool)
_stop_requests = {}

# In-memory store for active exploration sessions (session_id -> bool)
# Prevents duplicate exploration requests
_active_explorations = {}


@router.get("/{session_id}")
async def get_hypothesis_set(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the hypothesis set for a session.

    Returns the most recent hypothesis set with all hypotheses and test results.
    """
    try:
        # Get most recent hypothesis set for this session
        result = await db.execute(
            select(HypothesisSetDB)
            .where(HypothesisSetDB.session_id == session_id)
            .order_by(HypothesisSetDB.created_at.desc())
            .limit(1)
        )
        hypothesis_set_db = result.scalar_one_or_none()

        if not hypothesis_set_db:
            raise HTTPException(status_code=404, detail="No hypothesis set found for session")

        # Return the raw JSON directly - it's already serialized correctly
        return hypothesis_set_db.hypotheses_json
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving hypothesis set: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve hypothesis set: {str(e)}")


@router.post("/extract", response_model=HypothesisSet)
async def extract_hypotheses(
    data: HypothesisExtractionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Extract multiple competing style interpretations from a session's original image.

    Returns a HypothesisSet with untested hypotheses (all have equal initial confidence).
    """
    session_id = data.session_id

    # Get session
    await manager.broadcast_log(
        session_id, "Looking up session...", "info", "hypothesis_extract"
    )
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        await manager.broadcast_log(
            session_id, "Session not found", "error", "hypothesis_extract"
        )
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.original_image_path:
        await manager.broadcast_log(
            session_id, "No original image found", "error", "hypothesis_extract"
        )
        raise HTTPException(status_code=400, detail="Session has no original image")

    # Update status
    session.status = SessionStatus.HYPOTHESIS_EXPLORING.value
    await db.commit()

    try:
        # Load image
        await manager.broadcast_log(
            session_id, "Loading original image...", "info", "hypothesis_extract"
        )
        image_b64 = await storage_service.load_image_raw(session.original_image_path)

        # Extract hypotheses
        await manager.broadcast_progress(
            session_id, "hypothesis_extract", 20, "Extracting hypotheses"
        )

        hypothesis_set = await hypothesis_extractor.extract_hypotheses(
            image_b64=image_b64,
            session_id=session_id,
            num_hypotheses=data.num_hypotheses,
            style_hints=session.style_hints,
        )

        await manager.broadcast_progress(
            session_id, "hypothesis_extract", 100, "Extraction complete"
        )

        # Save to database
        hypothesis_set_db = HypothesisSetDB(
            session_id=session_id,
            hypotheses_json=hypothesis_set.model_dump(mode='json'),
            selected_hypothesis_id=None,
        )
        db.add(hypothesis_set_db)
        await db.commit()

        await manager.broadcast_log(
            session_id,
            f"Generated {len(hypothesis_set.hypotheses)} hypotheses",
            "success",
            "hypothesis_extract",
        )

        return hypothesis_set

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()
        await manager.broadcast_log(
            session_id, f"Hypothesis extraction failed: {e}", "error", "hypothesis_extract"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_hypothesis(
    data: HypothesisTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Test a specific hypothesis by generating images and scoring consistency.

    Updates the hypothesis with test results and new confidence score.
    """
    session_id = data.session_id

    # Get session
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get hypothesis set
    result = await db.execute(
        select(HypothesisSetDB)
        .where(HypothesisSetDB.session_id == session_id)
        .order_by(HypothesisSetDB.created_at.desc())
    )
    hypothesis_set_db = result.scalar_one_or_none()

    if not hypothesis_set_db:
        raise HTTPException(status_code=404, detail="No hypothesis set found for session")

    hypothesis_set = HypothesisSet(**hypothesis_set_db.hypotheses_json)

    # Find hypothesis to test
    hypothesis = hypothesis_set.get_hypothesis(data.hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    try:
        # Load original image
        image_b64 = await storage_service.load_image_raw(session.original_image_path)

        # Test hypothesis
        updated_hypothesis = await hypothesis_tester.test_hypothesis(
            hypothesis=hypothesis,
            original_image_b64=image_b64,
            test_subjects=data.test_subjects,
            session_id=session_id,
        )

        # Update hypothesis in set
        for idx, h in enumerate(hypothesis_set.hypotheses):
            if h.id == data.hypothesis_id:
                hypothesis_set.hypotheses[idx] = updated_hypothesis
                break

        # Save updated set
        hypothesis_set_db.hypotheses_json = hypothesis_set.model_dump(mode='json')
        await db.commit()

        await manager.broadcast_log(
            session_id,
            f"Hypothesis tested: confidence={updated_hypothesis.confidence:.2f}",
            "success",
            "hypothesis_test",
        )

        return updated_hypothesis

    except Exception as e:
        await manager.broadcast_log(
            session_id, f"Hypothesis testing failed: {e}", "error", "hypothesis_test"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explore", response_model=HypothesisExploreResponse)
async def explore_hypotheses(
    data: HypothesisExploreRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Full hypothesis exploration: extract + test all + rank + optionally select.

    This is the main endpoint for hypothesis mode.
    Returns all tested hypotheses ranked by confidence, and selected hypothesis if auto-selected.
    """
    session_id = data.session_id

    # Check if exploration is already running for this session
    if _active_explorations.get(session_id, False):
        logger.warning(f"Exploration already in progress for session {session_id}")
        raise HTTPException(
            status_code=409,
            detail="Exploration already in progress for this session"
        )

    # Mark this session as actively exploring
    _active_explorations[session_id] = True

    # Get session
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        _active_explorations.pop(session_id, None)
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.original_image_path:
        _active_explorations.pop(session_id, None)
        raise HTTPException(status_code=400, detail="Session has no original image")

    # Check if session is already exploring (double-check via status)
    if session.status == SessionStatus.HYPOTHESIS_EXPLORING.value:
        _active_explorations.pop(session_id, None)
        logger.warning(f"Session {session_id} is already in exploring status")
        raise HTTPException(
            status_code=409,
            detail="Session is already exploring"
        )

    # Update status
    session.status = SessionStatus.HYPOTHESIS_EXPLORING.value
    await db.commit()

    try:
        # Load image
        await manager.broadcast_log(
            session_id, "Loading original image...", "info", "hypothesis_explore"
        )
        image_b64 = await storage_service.load_image_raw(session.original_image_path)

        # Step 1: Extract hypotheses
        await manager.broadcast_progress(
            session_id, "hypothesis_explore", 10, "Extracting hypotheses"
        )

        hypothesis_set = await hypothesis_extractor.extract_hypotheses(
            image_b64=image_b64,
            session_id=session_id,
            num_hypotheses=data.num_hypotheses,
            style_hints=session.style_hints,
        )

        # Broadcast extracted hypotheses for progressive display
        await manager.send_to_session(
            session_id,
            "hypotheses_extracted",
            {
                "hypotheses": [
                    {
                        "id": h.id,
                        "interpretation": h.interpretation,
                        "supporting_evidence": h.supporting_evidence,
                        "uncertain_aspects": h.uncertain_aspects,
                    }
                    for h in hypothesis_set.hypotheses
                ],
            },
        )

        # Step 2: Test each hypothesis
        total_hypotheses = len(hypothesis_set.hypotheses)
        test_images_generated = 0

        for idx, hypothesis in enumerate(hypothesis_set.hypotheses):
            # Check if user requested stop
            if _stop_requests.get(session_id, False):
                _stop_requests.pop(session_id, None)
                _active_explorations.pop(session_id, None)  # Clear active flag
                await manager.broadcast_log(
                    session_id,
                    f"Exploration stopped by user at hypothesis {idx + 1}/{total_hypotheses}",
                    "warning",
                    "hypothesis_explore",
                )
                # Return partial results
                return HypothesisExploreResponse(
                    session_id=session_id,
                    hypotheses=hypothesis_set.hypotheses[:idx],  # Only completed hypotheses
                    selected_hypothesis=None,
                    auto_selected=False,
                    test_images_generated=test_images_generated,
                )

            progress = 10 + (idx + 1) * (70 / total_hypotheses)
            await manager.broadcast_progress(
                session_id,
                "hypothesis_explore",
                int(progress),
                f"Testing hypothesis {idx + 1}/{total_hypotheses}: {hypothesis.interpretation}",
            )

            # Broadcast that we're starting to test this hypothesis
            await manager.send_to_session(
                session_id,
                "hypothesis_testing_start",
                {
                    "hypothesis_id": hypothesis.id,
                    "hypothesis_index": idx,
                    "interpretation": hypothesis.interpretation,
                },
            )

            updated_hypothesis = await hypothesis_tester.test_hypothesis(
                hypothesis=hypothesis,
                original_image_b64=image_b64,
                test_subjects=data.test_subjects,
                session_id=session_id,
            )

            hypothesis_set.hypotheses[idx] = updated_hypothesis
            test_images_generated += len(updated_hypothesis.test_results)

            # Broadcast completed hypothesis with all test results
            await manager.send_to_session(
                session_id,
                "hypothesis_testing_complete",
                {
                    "hypothesis_id": hypothesis.id,
                    "hypothesis_index": idx,
                    "confidence": updated_hypothesis.confidence,
                    "test_results_count": len(updated_hypothesis.test_results),
                },
            )

        # Step 3: Rank and optionally select
        await manager.broadcast_progress(
            session_id, "hypothesis_explore", 85, "Ranking hypotheses"
        )

        selected_hypothesis = None
        auto_selected = False

        if data.auto_select:
            selected_hypothesis, auto_selected = await hypothesis_selector.select_best(
                hypothesis_set=hypothesis_set,
                auto_select_threshold=data.auto_select_threshold,
                session_id=session_id,
            )

            if selected_hypothesis:
                hypothesis_set.selected_hypothesis_id = selected_hypothesis.id

        # Save to database
        hypothesis_set_db = HypothesisSetDB(
            session_id=session_id,
            hypotheses_json=hypothesis_set.model_dump(mode='json'),
            selected_hypothesis_id=hypothesis_set.selected_hypothesis_id,
        )
        db.add(hypothesis_set_db)

        # Update session status
        if hypothesis_set.selected_hypothesis_id:
            session.status = SessionStatus.HYPOTHESIS_READY.value
        else:
            session.status = SessionStatus.HYPOTHESIS_READY.value

        await db.commit()

        await manager.broadcast_progress(
            session_id, "hypothesis_explore", 100, "Exploration complete"
        )

        await manager.broadcast_log(
            session_id,
            f"Exploration complete: {total_hypotheses} hypotheses, "
            f"{test_images_generated} test images",
            "success",
            "hypothesis_explore",
        )

        # Clear active exploration flag
        _active_explorations.pop(session_id, None)

        return HypothesisExploreResponse(
            session_id=session_id,
            hypotheses=hypothesis_set.hypotheses,
            selected_hypothesis=selected_hypothesis,
            auto_selected=auto_selected,
            test_images_generated=test_images_generated,
        )

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()

        # Clear active exploration flag on error
        _active_explorations.pop(session_id, None)

        await manager.broadcast_log(
            session_id, f"Hypothesis exploration failed: {e}", "error", "hypothesis_explore"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/select", response_model=StyleProfile)
async def select_hypothesis(
    data: HypothesisSelectRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually select a hypothesis and promote its profile to be the session's style profile.

    Creates a StyleProfileDB entry with version 1 for the selected hypothesis.
    """
    session_id = data.session_id

    # Get session
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get hypothesis set
    result = await db.execute(
        select(HypothesisSetDB)
        .where(HypothesisSetDB.session_id == session_id)
        .order_by(HypothesisSetDB.created_at.desc())
    )
    hypothesis_set_db = result.scalar_one_or_none()

    if not hypothesis_set_db:
        raise HTTPException(status_code=404, detail="No hypothesis set found for session")

    hypothesis_set = HypothesisSet(**hypothesis_set_db.hypotheses_json)

    # Select hypothesis
    try:
        selected_hypothesis = await hypothesis_selector.manual_select(
            hypothesis_set=hypothesis_set,
            hypothesis_id=data.hypothesis_id,
            session_id=session_id,
        )

        # Update hypothesis set in database
        hypothesis_set.selected_hypothesis_id = data.hypothesis_id
        hypothesis_set_db.hypotheses_json = hypothesis_set.model_dump(mode='json')
        hypothesis_set_db.selected_hypothesis_id = data.hypothesis_id

        # Create StyleProfileDB entry (version 1)
        style_profile_db = StyleProfileDB(
            session_id=session_id,
            version=1,
            profile_json=selected_hypothesis.profile.model_dump(mode='json'),
        )
        db.add(style_profile_db)

        # Update session status
        session.status = SessionStatus.READY.value
        await db.commit()

        await manager.broadcast_log(
            session_id,
            f"Hypothesis selected: {selected_hypothesis.interpretation}",
            "success",
            "hypothesis_select",
        )

        return selected_hypothesis.profile

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await manager.broadcast_log(
            session_id, f"Hypothesis selection failed: {e}", "error", "hypothesis_select"
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_exploration(data: dict):
    """
    Request immediate stop of hypothesis exploration for a session.
    Cancels ongoing ComfyUI and VLM requests.
    """
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Set stop flag
    _stop_requests[session_id] = True

    try:
        # Cancel ongoing VLM requests for this session
        vlm_service.cancel_request(session_id)

        # Cancel ongoing ComfyUI requests for this session
        comfyui_service.cancel_request(session_id)

        # Send interrupt to ComfyUI to stop current generation immediately
        await comfyui_service.interrupt()

        # Clear the entire ComfyUI queue to stop all pending generations
        await comfyui_service.clear_queue()

        logger.info(f"Stop requested for session {session_id} - cancelled VLM and ComfyUI requests, cleared queue")
    except Exception as e:
        logger.warning(f"Error during stop cleanup for session {session_id}: {e}")
        # Continue anyway - stop flag is set

    await manager.broadcast_log(
        session_id,
        "Stop requested - cancelled ongoing operations and cleared queue...",
        "warning",
        "hypothesis_explore"
    )

    return {
        "session_id": session_id,
        "message": "Stop requested - cancelled ongoing operations and cleared queue",
    }
