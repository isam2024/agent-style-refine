"""
Style Explorer API Router

Endpoints for divergent style exploration - creating and navigating
style variations through mutation strategies.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import (
    StyleProfile,
    MutationStrategy,
    ExplorationStatus,
    ExplorationSessionCreate,
    ExplorationSessionResponse,
    ExplorationSessionSummary,
    ExplorationSnapshotResponse,
    ExplorationScores,
    ExploreRequest,
    ExploreResponse,
    SnapshotUpdateRequest,
    SnapshotToStyleRequest,
)
from backend.services.prompt_writer import prompt_writer
from backend.models.db_models import (
    ExplorationSession,
    ExplorationSnapshot,
    TrainedStyle,
)
from backend.services.storage import storage_service
from backend.services.explorer import style_explorer

router = APIRouter(prefix="/api/explorer", tags=["explorer"])


# ============================================================
# Session Management
# ============================================================

@router.post("/sessions", response_model=ExplorationSessionResponse)
async def create_exploration_session(
    data: ExplorationSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new exploration session from a reference image.

    This extracts the base style from the image and prepares
    for divergent exploration.
    """
    import uuid

    # Generate session ID upfront so we can save the image first
    session_id = str(uuid.uuid4())

    # Save reference image first
    image_path = await storage_service.save_image(
        session_id, data.image_b64, "reference.png"
    )

    # Extract base style profile before creating DB record
    try:
        base_profile = await style_explorer.extract_base_style(
            image_b64=data.image_b64,
            session_id=session_id,
        )
    except Exception as e:
        # Clean up the image if extraction fails
        storage_service.delete_session(session_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract base style: {str(e)}"
        )

    # Now create the session with all required fields
    session = ExplorationSession(
        id=session_id,
        name=data.name,
        reference_image_path=str(image_path),
        base_style_profile_json=base_profile.model_dump(),
        status=ExplorationStatus.PAUSED.value,  # Ready to explore, not actively exploring
        preferred_strategies_json=[s.value for s in data.preferred_strategies],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return ExplorationSessionResponse(
        id=session.id,
        name=session.name,
        reference_image_path=session.reference_image_path,
        base_style_profile=StyleProfile(**session.base_style_profile_json),
        status=ExplorationStatus(session.status),
        total_snapshots=session.total_snapshots,
        current_snapshot_id=session.current_snapshot_id,
        preferred_strategies=session.preferred_strategies_json,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions", response_model=list[ExplorationSessionSummary])
async def list_exploration_sessions(db: AsyncSession = Depends(get_db)):
    """List all exploration sessions."""
    result = await db.execute(
        select(ExplorationSession)
        .order_by(ExplorationSession.created_at.desc())
    )
    sessions = result.scalars().all()

    return [
        ExplorationSessionSummary(
            id=s.id,
            name=s.name,
            status=ExplorationStatus(s.status),
            total_snapshots=s.total_snapshots,
            created_at=s.created_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=dict)
async def get_exploration_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed exploration session with all snapshots."""
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # Load reference image (raw base64, no data URL prefix)
    reference_image_b64 = None
    if session.reference_image_path:
        try:
            reference_image_b64 = await storage_service.load_image_raw(
                session.reference_image_path
            )
        except FileNotFoundError:
            pass

    # Build snapshots list with images
    snapshots = []
    for snap in sorted(session.snapshots, key=lambda s: s.created_at):
        snap_data = {
            "id": snap.id,
            "parent_id": snap.parent_id,
            "style_profile": snap.style_profile_json,
            "prompt_used": snap.prompt_used,
            "mutation_strategy": snap.mutation_strategy,
            "mutation_description": snap.mutation_description,
            "scores": {
                "novelty": snap.novelty_score,
                "coherence": snap.coherence_score,
                "interest": snap.interest_score,
                "combined": snap.combined_score,
            } if snap.novelty_score is not None else None,
            "depth": snap.depth,
            "branch_name": snap.branch_name,
            "is_favorite": snap.is_favorite,
            "user_notes": snap.user_notes,
            "created_at": snap.created_at.isoformat(),
        }

        # Load snapshot image (raw base64, no data URL prefix)
        try:
            snap_data["image_b64"] = await storage_service.load_image_raw(
                snap.generated_image_path
            )
        except FileNotFoundError:
            snap_data["image_b64"] = None

        snapshots.append(snap_data)

    return {
        "id": session.id,
        "name": session.name,
        "status": session.status,
        "reference_image_b64": reference_image_b64,
        "base_style_profile": session.base_style_profile_json,
        "preferred_strategies": session.preferred_strategies_json,
        "current_snapshot_id": session.current_snapshot_id,
        "total_snapshots": session.total_snapshots,
        "snapshots": snapshots,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.delete("/sessions/{session_id}")
async def delete_exploration_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an exploration session and all its snapshots."""
    result = await db.execute(
        select(ExplorationSession)
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # Delete files
    storage_service.delete_session(session_id)

    # Delete from database (cascades to snapshots)
    await db.delete(session)
    await db.commit()

    return {"status": "deleted", "session_id": session_id}


# ============================================================
# Exploration Control
# ============================================================

@router.post("/sessions/{session_id}/explore", response_model=ExploreResponse)
async def run_exploration_step(
    session_id: str,
    data: ExploreRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run one exploration step.

    Applies a mutation strategy to create a new style variation,
    generates an image, scores it, and saves as a snapshot.
    """
    # Get session with snapshots
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # Determine parent snapshot
    parent_snapshot = None
    parent_image_b64 = None
    current_profile = StyleProfile(**session.base_style_profile_json)
    parent_depth = -1

    if data.parent_snapshot_id:
        # Branch from specific snapshot
        for snap in session.snapshots:
            if snap.id == data.parent_snapshot_id:
                parent_snapshot = snap
                current_profile = StyleProfile(**snap.style_profile_json)
                parent_depth = snap.depth
                break

        if parent_snapshot is None:
            raise HTTPException(status_code=404, detail="Parent snapshot not found")

        # Load parent image for comparison
        try:
            parent_image_b64 = await storage_service.load_image_raw(
                parent_snapshot.generated_image_path
            )
        except FileNotFoundError:
            pass

    elif session.current_snapshot_id:
        # Continue from current snapshot
        for snap in session.snapshots:
            if snap.id == session.current_snapshot_id:
                parent_snapshot = snap
                current_profile = StyleProfile(**snap.style_profile_json)
                parent_depth = snap.depth
                break

        if parent_snapshot:
            try:
                parent_image_b64 = await storage_service.load_image_raw(
                    parent_snapshot.generated_image_path
                )
            except FileNotFoundError:
                pass
    else:
        # First exploration - use reference image as parent for comparison
        try:
            parent_image_b64 = await storage_service.load_image_raw(
                session.reference_image_path
            )
        except FileNotFoundError:
            pass

    # Determine strategy
    strategy = data.strategy
    preferred_strategies = None
    if strategy is None:
        preferred_strategies = [
            MutationStrategy(s) for s in session.preferred_strategies_json
        ]

    # Get subject from base profile or use default
    subject = current_profile.suggested_test_prompt or current_profile.original_subject or "abstract scene"

    # Run exploration step
    session.status = ExplorationStatus.EXPLORING.value
    await db.commit()

    try:
        mutated_profile, mutation_description, image_b64, prompt_used, scores = \
            await style_explorer.explore_step(
                current_profile=current_profile,
                parent_image_b64=parent_image_b64,
                subject=subject,
                strategy=strategy,
                preferred_strategies=preferred_strategies,
                session_id=session_id,
            )

        # Save generated image
        snapshot_num = session.total_snapshots + 1
        image_filename = f"snapshot_{snapshot_num:03d}.png"
        image_path = await storage_service.save_image(
            session_id, image_b64, image_filename
        )

        # Create snapshot record
        snapshot = ExplorationSnapshot(
            session_id=session_id,
            parent_id=parent_snapshot.id if parent_snapshot else None,
            style_profile_json=mutated_profile.model_dump(),
            generated_image_path=str(image_path),
            prompt_used=prompt_used,
            mutation_strategy=strategy.value if strategy else "random_dimension",
            mutation_description=mutation_description,
            novelty_score=scores.novelty,
            coherence_score=scores.coherence,
            interest_score=scores.interest,
            combined_score=scores.combined,
            depth=parent_depth + 1,
        )
        db.add(snapshot)

        # Update session
        session.total_snapshots = snapshot_num
        session.current_snapshot_id = snapshot.id
        session.status = ExplorationStatus.PAUSED.value  # Ready for more exploration

        await db.commit()
        await db.refresh(snapshot)

        # Build response
        return ExploreResponse(
            snapshot=ExplorationSnapshotResponse(
                id=snapshot.id,
                session_id=snapshot.session_id,
                parent_id=snapshot.parent_id,
                style_profile=mutated_profile,
                generated_image_path=snapshot.generated_image_path,
                prompt_used=snapshot.prompt_used,
                mutation_strategy=snapshot.mutation_strategy,
                mutation_description=snapshot.mutation_description,
                scores=ExplorationScores(
                    novelty=scores.novelty,
                    coherence=scores.coherence,
                    interest=scores.interest,
                    combined=scores.combined,
                ),
                depth=snapshot.depth,
                branch_name=snapshot.branch_name,
                is_favorite=snapshot.is_favorite,
                user_notes=snapshot.user_notes,
                created_at=snapshot.created_at,
            ),
            image_b64=image_b64,
        )

    except Exception as e:
        session.status = ExplorationStatus.PAUSED.value
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Exploration step failed: {str(e)}"
        )


# ============================================================
# Snapshot Management
# ============================================================

@router.get("/sessions/{session_id}/snapshots", response_model=list[dict])
async def list_snapshots(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all snapshots for a session."""
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(ExplorationSnapshot.session_id == session_id)
        .order_by(ExplorationSnapshot.created_at)
    )
    snapshots = result.scalars().all()

    return [
        {
            "id": s.id,
            "parent_id": s.parent_id,
            "mutation_strategy": s.mutation_strategy,
            "mutation_description": s.mutation_description,
            "scores": {
                "novelty": s.novelty_score,
                "coherence": s.coherence_score,
                "interest": s.interest_score,
                "combined": s.combined_score,
            } if s.novelty_score is not None else None,
            "depth": s.depth,
            "is_favorite": s.is_favorite,
            "created_at": s.created_at.isoformat(),
        }
        for s in snapshots
    ]


@router.get("/snapshots/{snapshot_id}", response_model=dict)
async def get_snapshot(
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed snapshot information."""
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(ExplorationSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Load image (raw base64, no data URL prefix)
    image_b64 = None
    try:
        image_b64 = await storage_service.load_image_raw(snapshot.generated_image_path)
    except FileNotFoundError:
        pass

    return {
        "id": snapshot.id,
        "session_id": snapshot.session_id,
        "parent_id": snapshot.parent_id,
        "style_profile": snapshot.style_profile_json,
        "generated_image_path": snapshot.generated_image_path,
        "image_b64": image_b64,
        "prompt_used": snapshot.prompt_used,
        "mutation_strategy": snapshot.mutation_strategy,
        "mutation_description": snapshot.mutation_description,
        "scores": {
            "novelty": snapshot.novelty_score,
            "coherence": snapshot.coherence_score,
            "interest": snapshot.interest_score,
            "combined": snapshot.combined_score,
        } if snapshot.novelty_score is not None else None,
        "depth": snapshot.depth,
        "branch_name": snapshot.branch_name,
        "is_favorite": snapshot.is_favorite,
        "user_notes": snapshot.user_notes,
        "created_at": snapshot.created_at.isoformat(),
    }


@router.patch("/snapshots/{snapshot_id}", response_model=dict)
async def update_snapshot(
    snapshot_id: str,
    data: SnapshotUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update snapshot metadata (favorite, notes, branch name)."""
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(ExplorationSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if data.is_favorite is not None:
        snapshot.is_favorite = data.is_favorite
    if data.user_notes is not None:
        snapshot.user_notes = data.user_notes
    if data.branch_name is not None:
        snapshot.branch_name = data.branch_name

    await db.commit()
    await db.refresh(snapshot)

    return {
        "id": snapshot.id,
        "is_favorite": snapshot.is_favorite,
        "user_notes": snapshot.user_notes,
        "branch_name": snapshot.branch_name,
        "updated": True,
    }


@router.post("/snapshots/{snapshot_id}/favorite", response_model=dict)
async def toggle_favorite(
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle favorite status of a snapshot."""
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(ExplorationSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    snapshot.is_favorite = not snapshot.is_favorite
    await db.commit()

    return {
        "id": snapshot.id,
        "is_favorite": snapshot.is_favorite,
    }


# ============================================================
# Tree Navigation & Auto-Explore
# ============================================================

@router.get("/sessions/{session_id}/tree", response_model=dict)
async def get_exploration_tree(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the exploration tree structure for visualization.

    Returns a hierarchical structure showing parent-child relationships
    between snapshots, useful for tree/graph visualizations.
    """
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # Build tree nodes
    nodes = []
    max_depth = 0

    for snap in session.snapshots:
        # Count children for this snapshot
        children_count = sum(1 for s in session.snapshots if s.parent_id == snap.id)

        nodes.append({
            "id": snap.id,
            "parent_id": snap.parent_id,
            "depth": snap.depth,
            "mutation_strategy": snap.mutation_strategy,
            "mutation_description": snap.mutation_description[:50] + "..." if len(snap.mutation_description) > 50 else snap.mutation_description,
            "combined_score": snap.combined_score,
            "is_favorite": snap.is_favorite,
            "children_count": children_count,
            "image_path": snap.generated_image_path,
        })

        if snap.depth > max_depth:
            max_depth = snap.depth

    # Find root nodes (depth=0 or no parent)
    root_nodes = [n for n in nodes if n["parent_id"] is None]

    return {
        "session_id": session_id,
        "root_nodes": root_nodes,
        "all_nodes": nodes,
        "total_nodes": len(nodes),
        "max_depth": max_depth,
        "current_snapshot_id": session.current_snapshot_id,
    }


@router.post("/sessions/{session_id}/auto-explore", response_model=dict)
async def auto_explore(
    session_id: str,
    num_steps: int = 5,
    branch_threshold: float = 85.0,
    parent_snapshot_id: str | None = Query(None, description="Snapshot to start from (overrides current_snapshot_id)"),
    strategy: str | None = Query(None, description="Specific strategy to use (overrides session preferred_strategies)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Auto-run multiple exploration steps.

    Continues from the specified snapshot (or current snapshot), running up to
    num_steps exploration iterations. Each step chains from the previous.

    Args:
        session_id: The exploration session
        num_steps: Number of exploration steps to run (1-20)
        branch_threshold: Auto-branch if combined score exceeds this (0-100)
        parent_snapshot_id: Snapshot to start from (optional, defaults to current)
        strategy: Specific strategy to use for all steps (optional, overrides session defaults)

    Returns:
        Summary of the auto-exploration run
    """
    if num_steps < 1 or num_steps > 20:
        raise HTTPException(status_code=400, detail="num_steps must be between 1 and 20")

    # Get session
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # If parent_snapshot_id provided, set it as the starting point
    starting_snapshot_id = parent_snapshot_id or session.current_snapshot_id

    session.status = ExplorationStatus.EXPLORING.value
    await db.commit()

    snapshots_created = []
    best_snapshot_id = None
    best_score = 0.0
    stopped_reason = "completed"

    try:
        for step in range(num_steps):
            # Reload session to get updated snapshots (need fresh query for relationships)
            result = await db.execute(
                select(ExplorationSession)
                .options(selectinload(ExplorationSession.snapshots))
                .where(ExplorationSession.id == session_id)
            )
            session = result.scalar_one()

            # Determine current state - use starting_snapshot_id for first step,
            # then follow the chain via current_snapshot_id
            parent_snapshot = None
            parent_image_b64 = None
            current_profile = StyleProfile(**session.base_style_profile_json)
            parent_depth = -1

            # For first step, use starting_snapshot_id; for subsequent steps, use current_snapshot_id
            target_snapshot_id = starting_snapshot_id if step == 0 else session.current_snapshot_id

            if target_snapshot_id:
                for snap in session.snapshots:
                    if snap.id == target_snapshot_id:
                        parent_snapshot = snap
                        current_profile = StyleProfile(**snap.style_profile_json)
                        parent_depth = snap.depth
                        break

                if parent_snapshot:
                    try:
                        parent_image_b64 = await storage_service.load_image_raw(
                            parent_snapshot.generated_image_path
                        )
                    except FileNotFoundError:
                        pass
            else:
                try:
                    parent_image_b64 = await storage_service.load_image_raw(
                        session.reference_image_path
                    )
                except FileNotFoundError:
                    pass

            # Determine strategy - use explicit strategy if provided, otherwise use session defaults
            use_strategy = None
            preferred_strategies = None
            if strategy:
                # Explicit strategy overrides session defaults
                use_strategy = MutationStrategy(strategy)
            else:
                # Fall back to session's preferred strategies
                preferred_strategies = [
                    MutationStrategy(s) for s in session.preferred_strategies_json
                ]

            # Get subject
            subject = current_profile.suggested_test_prompt or current_profile.original_subject or "abstract scene"

            # Run exploration step
            mutated_profile, mutation_description, image_b64, prompt_used, scores = \
                await style_explorer.explore_step(
                    current_profile=current_profile,
                    parent_image_b64=parent_image_b64,
                    subject=subject,
                    strategy=use_strategy,
                    preferred_strategies=preferred_strategies,
                    session_id=session_id,
                )

            # Save generated image
            snapshot_num = session.total_snapshots + 1
            image_filename = f"snapshot_{snapshot_num:03d}.png"
            image_path = await storage_service.save_image(
                session_id, image_b64, image_filename
            )

            # Create snapshot
            snapshot = ExplorationSnapshot(
                session_id=session_id,
                parent_id=parent_snapshot.id if parent_snapshot else None,
                style_profile_json=mutated_profile.model_dump(),
                generated_image_path=str(image_path),
                prompt_used=prompt_used,
                mutation_strategy=mutation_description.split(":")[0] if ":" in mutation_description else "random_dimension",
                mutation_description=mutation_description,
                novelty_score=scores.novelty,
                coherence_score=scores.coherence,
                interest_score=scores.interest,
                combined_score=scores.combined,
                depth=parent_depth + 1,
            )
            db.add(snapshot)

            # Update session
            session.total_snapshots = snapshot_num
            session.current_snapshot_id = snapshot.id

            await db.commit()
            await db.refresh(snapshot)

            snapshots_created.append({
                "id": snapshot.id,
                "combined_score": scores.combined,
                "mutation": mutation_description[:50],
            })

            # Track best
            if scores.combined > best_score:
                best_score = scores.combined
                best_snapshot_id = snapshot.id

            # Check branch threshold
            if scores.combined >= branch_threshold:
                snapshot.is_favorite = True
                await db.commit()
                stopped_reason = "threshold_reached"
                break

    except Exception as e:
        session.status = ExplorationStatus.PAUSED.value
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Auto-explore failed at step {len(snapshots_created) + 1}: {str(e)}"
        )

    # Set status to paused (ready for more exploration) when complete
    session.status = ExplorationStatus.PAUSED.value
    await db.commit()

    return {
        "session_id": session_id,
        "snapshots_created": len(snapshots_created),
        "snapshots": snapshots_created,
        "best_snapshot_id": best_snapshot_id,
        "best_score": best_score,
        "stopped_reason": stopped_reason,
    }


@router.post("/sessions/{session_id}/batch-explore", response_model=dict)
async def batch_explore(
    session_id: str,
    strategies: list[MutationStrategy] = Query(..., description="List of strategies to run"),
    iterations: int = Query(1, ge=1, le=20, description="Number of times to run each strategy"),
    parent_snapshot_id: str | None = Query(None, description="Snapshot to branch from"),
    db: AsyncSession = Depends(get_db),
):
    """
    Run multiple mutation strategies from the same parent.

    This creates multiple branches at once, each using a different strategy.
    Useful for comparing how different mutations diverge from the same point.

    Args:
        session_id: The exploration session
        strategies: List of strategies to run (each creates a new branch)
        iterations: Number of times to run each strategy (default 1)
        parent_snapshot_id: Snapshot to branch from, or None for current

    Returns:
        List of created snapshots with their scores
    """
    if not strategies:
        raise HTTPException(status_code=400, detail="At least one strategy is required")

    total_runs = len(strategies) * iterations
    if total_runs > 20:
        raise HTTPException(status_code=400, detail=f"Maximum 20 total runs (you requested {total_runs})")

    # Get session
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    session.status = ExplorationStatus.EXPLORING.value
    await db.commit()

    # Determine parent
    parent_snapshot = None
    parent_image_b64 = None
    current_profile = StyleProfile(**session.base_style_profile_json)
    parent_depth = -1

    if parent_snapshot_id:
        for snap in session.snapshots:
            if snap.id == parent_snapshot_id:
                parent_snapshot = snap
                current_profile = StyleProfile(**snap.style_profile_json)
                parent_depth = snap.depth
                break
    elif session.current_snapshot_id:
        for snap in session.snapshots:
            if snap.id == session.current_snapshot_id:
                parent_snapshot = snap
                current_profile = StyleProfile(**snap.style_profile_json)
                parent_depth = snap.depth
                break

    # Load parent image
    if parent_snapshot:
        try:
            parent_image_b64 = await storage_service.load_image_raw(
                parent_snapshot.generated_image_path
            )
        except FileNotFoundError:
            pass
    else:
        try:
            parent_image_b64 = await storage_service.load_image_raw(
                session.reference_image_path
            )
        except FileNotFoundError:
            pass

    # Get subject
    subject = current_profile.suggested_test_prompt or current_profile.original_subject or "abstract scene"

    # Run each strategy for the specified number of iterations
    results = []
    for iteration in range(iterations):
        for strategy in strategies:
            try:
                # Run exploration step
                mutated_profile, mutation_description, image_b64, prompt_used, scores = \
                    await style_explorer.explore_step(
                        current_profile=current_profile,
                        parent_image_b64=parent_image_b64,
                        subject=subject,
                        strategy=strategy,
                        preferred_strategies=[strategy],
                        session_id=session_id,
                    )

                # Save generated image
                snapshot_num = session.total_snapshots + 1
                image_filename = f"snapshot_{snapshot_num:03d}.png"
                image_path = await storage_service.save_image(
                    session_id, image_b64, image_filename
                )

                # Create snapshot
                snapshot = ExplorationSnapshot(
                    session_id=session_id,
                    parent_id=parent_snapshot.id if parent_snapshot else None,
                    style_profile_json=mutated_profile.model_dump(),
                    generated_image_path=str(image_path),
                    prompt_used=prompt_used,
                    mutation_strategy=strategy.value,
                    mutation_description=mutation_description,
                    novelty_score=scores.novelty,
                    coherence_score=scores.coherence,
                    interest_score=scores.interest,
                    combined_score=scores.combined,
                    depth=parent_depth + 1,
                )
                db.add(snapshot)

                # Update session
                session.total_snapshots = snapshot_num

                await db.commit()
                await db.refresh(snapshot)

                results.append({
                    "id": snapshot.id,
                    "strategy": strategy.value,
                    "iteration": iteration + 1,
                    "mutation_description": mutation_description,
                    "combined_score": scores.combined,
                    "image_b64": image_b64,
                })

            except Exception as e:
                results.append({
                    "strategy": strategy.value,
                    "iteration": iteration + 1,
                    "error": str(e),
                })

    session.status = ExplorationStatus.PAUSED.value
    await db.commit()

    return {
        "session_id": session_id,
        "parent_snapshot_id": parent_snapshot.id if parent_snapshot else None,
        "results": results,
        "successful": len([r for r in results if "id" in r]),
        "failed": len([r for r in results if "error" in r]),
    }


@router.post("/sessions/{session_id}/set-current", response_model=dict)
async def set_current_snapshot(
    session_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Set the current snapshot for a session.

    This determines which snapshot future explorations will branch from
    when no explicit parent is specified.
    """
    result = await db.execute(
        select(ExplorationSession)
        .options(selectinload(ExplorationSession.snapshots))
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    # Verify snapshot exists and belongs to session
    snapshot_found = False
    for snap in session.snapshots:
        if snap.id == snapshot_id:
            snapshot_found = True
            break

    if not snapshot_found:
        raise HTTPException(status_code=404, detail="Snapshot not found in this session")

    session.current_snapshot_id = snapshot_id
    await db.commit()

    return {
        "session_id": session_id,
        "current_snapshot_id": snapshot_id,
        "updated": True,
    }


@router.post("/sessions/{session_id}/reset-status", response_model=dict)
async def reset_session_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Reset a stuck session's status to 'paused'.

    Use this if a session got stuck in 'exploring' status.
    """
    result = await db.execute(
        select(ExplorationSession)
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    old_status = session.status
    session.status = ExplorationStatus.PAUSED.value
    await db.commit()

    return {
        "session_id": session_id,
        "old_status": old_status,
        "new_status": session.status,
        "reset": True,
    }


@router.patch("/sessions/{session_id}/strategies", response_model=dict)
async def update_preferred_strategies(
    session_id: str,
    strategies: list[MutationStrategy],
    db: AsyncSession = Depends(get_db),
):
    """
    Update the preferred mutation strategies for a session.

    These strategies are used when auto-exploring or when no specific
    strategy is requested.
    """
    if not strategies:
        raise HTTPException(status_code=400, detail="At least one strategy is required")

    result = await db.execute(
        select(ExplorationSession)
        .where(ExplorationSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Exploration session not found")

    session.preferred_strategies_json = [s.value for s in strategies]
    await db.commit()

    return {
        "session_id": session_id,
        "preferred_strategies": session.preferred_strategies_json,
        "updated": True,
    }


@router.get("/sessions/{session_id}/favorites", response_model=list[dict])
async def get_favorite_snapshots(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all favorite snapshots for a session."""
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(
            ExplorationSnapshot.session_id == session_id,
            ExplorationSnapshot.is_favorite == True
        )
        .order_by(ExplorationSnapshot.combined_score.desc())
    )
    snapshots = result.scalars().all()

    favorites = []
    for s in snapshots:
        snap_data = {
            "id": s.id,
            "parent_id": s.parent_id,
            "mutation_strategy": s.mutation_strategy,
            "mutation_description": s.mutation_description,
            "scores": {
                "novelty": s.novelty_score,
                "coherence": s.coherence_score,
                "interest": s.interest_score,
                "combined": s.combined_score,
            },
            "depth": s.depth,
            "branch_name": s.branch_name,
            "user_notes": s.user_notes,
            "created_at": s.created_at.isoformat(),
        }

        # Load image (raw base64, no data URL prefix)
        try:
            snap_data["image_b64"] = await storage_service.load_image_raw(
                s.generated_image_path
            )
        except FileNotFoundError:
            snap_data["image_b64"] = None

        favorites.append(snap_data)

    return favorites


@router.post("/snapshots/{snapshot_id}/to-style", response_model=dict)
async def convert_snapshot_to_style(
    snapshot_id: str,
    data: SnapshotToStyleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Convert an exploration snapshot to a trained style.

    This allows exporting interesting discoveries from exploration
    as reusable style agents for the prompt writer.

    Generates comprehensive style rules as a "style guide" with:
    - technique_keywords: How to render this style
    - mood_keywords: The atmosphere/feeling
    - always_include: Critical elements that define this style
    - always_avoid: Things that would break this style
    - emphasize: Key traits to push
    - de_emphasize: Traits to minimize
    """
    result = await db.execute(
        select(ExplorationSnapshot)
        .where(ExplorationSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Load snapshot image for thumbnail
    thumbnail_b64 = None
    try:
        thumbnail_b64 = await storage_service.load_image_raw(
            snapshot.generated_image_path
        )
    except FileNotFoundError:
        pass

    # Parse the style profile
    style_profile = StyleProfile(**snapshot.style_profile_json)

    # Generate comprehensive style rules from the profile
    # This creates the "style guide" with do/don't rules
    style_rules = prompt_writer.extract_rules_from_profile(
        style_profile=style_profile,
        iteration_history=None,  # No iteration history for exploration exports
    )

    # Enhance the rules based on the mutation that created this style
    mutation_desc = snapshot.mutation_description or ""

    # Add mutation-specific guidance to always_include
    if "Time Shift" in mutation_desc:
        era = mutation_desc.replace("Time Shift: Transported to ", "").replace(" era", "")
        style_rules.always_include.insert(0, f"{era} aesthetic throughout")
    elif "Medium Swap" in mutation_desc:
        medium = mutation_desc.replace("Medium Swap: Rendered as ", "")
        style_rules.always_include.insert(0, f"rendered as {medium}")
    elif "Mood Shift" in mutation_desc:
        mood = mutation_desc.replace("Mood Shift: Transformed to ", "")
        style_rules.mood_keywords.insert(0, mood)
    elif "Culture Shift" in mutation_desc:
        culture = mutation_desc.replace("Culture Shift: Applied ", "").replace(" aesthetic", "")
        style_rules.always_include.insert(0, f"{culture} cultural aesthetic")
    elif "Decay" in mutation_desc:
        style_rules.always_include.insert(0, "weathered, aged, decayed appearance")
    elif "Constrain" in mutation_desc:
        constraint = mutation_desc.replace("Constrain: Applied ", "").replace(" constraint", "")
        style_rules.always_include.insert(0, f"{constraint} constraint strictly enforced")

    # Convert style_rules to dict for JSON storage
    style_rules_dict = {
        "always_include": style_rules.always_include,
        "always_avoid": style_rules.always_avoid,
        "technique_keywords": style_rules.technique_keywords,
        "mood_keywords": style_rules.mood_keywords,
        "emphasize": style_rules.emphasize,
        "de_emphasize": style_rules.de_emphasize,
    }

    # Create trained style from snapshot
    style = TrainedStyle(
        name=data.name,
        description=data.description or f"Explored from {snapshot.mutation_description}",
        style_profile_json=snapshot.style_profile_json,
        style_rules_json=style_rules_dict,
        training_summary_json={
            "source": "exploration",
            "mutation_strategy": snapshot.mutation_strategy,
            "mutation_description": snapshot.mutation_description,
            "scores": {
                "novelty": snapshot.novelty_score,
                "coherence": snapshot.coherence_score,
                "interest": snapshot.interest_score,
                "combined": snapshot.combined_score,
            },
        },
        thumbnail_b64=thumbnail_b64,
        source_session_id=None,  # Not from training session
        iterations_trained=0,
        final_score=int(snapshot.combined_score) if snapshot.combined_score else None,
        tags_json=data.tags,
    )
    db.add(style)
    await db.commit()
    await db.refresh(style)

    return {
        "id": style.id,
        "name": style.name,
        "description": style.description,
        "style_rules": style_rules_dict,  # Return the generated rules for visibility
        "created": True,
    }
