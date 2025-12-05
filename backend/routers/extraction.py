from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.schemas import ExtractionRequest, StyleProfile, SessionStatus
from backend.models.db_models import Session, StyleProfileDB
from backend.services.storage import storage_service
from backend.services.extractor import style_extractor

router = APIRouter(prefix="/api/extract", tags=["extraction"])


@router.post("/", response_model=StyleProfile)
async def extract_style(
    data: ExtractionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Extract style profile from a session's original image."""
    # Get session
    result = await db.execute(select(Session).where(Session.id == data.session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.original_image_path:
        raise HTTPException(status_code=400, detail="Session has no original image")

    # Update status
    session.status = SessionStatus.EXTRACTING.value
    await db.commit()

    try:
        # Load image and extract style
        image_b64 = await storage_service.load_image_raw(session.original_image_path)
        style_profile = await style_extractor.extract(image_b64)

        # Save to database as version 1
        profile_db = StyleProfileDB(
            session_id=session.id,
            version=1,
            profile_json=style_profile.model_dump(),
        )
        db.add(profile_db)

        session.status = SessionStatus.READY.value
        await db.commit()

        return style_profile

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reextract", response_model=StyleProfile)
async def reextract_style(
    data: ExtractionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Re-extract style profile, creating a new version."""
    # Get session with existing profiles
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.style_profiles))
        .where(Session.id == data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.original_image_path:
        raise HTTPException(status_code=400, detail="Session has no original image")

    # Update status
    session.status = SessionStatus.EXTRACTING.value
    await db.commit()

    try:
        # Load image and extract style
        image_b64 = await storage_service.load_image_raw(session.original_image_path)
        style_profile = await style_extractor.extract(image_b64)

        # Determine new version number
        current_version = max(
            (sp.version for sp in session.style_profiles), default=0
        )
        new_version = current_version + 1

        # Save to database as new version
        profile_db = StyleProfileDB(
            session_id=session.id,
            version=new_version,
            profile_json=style_profile.model_dump(),
        )
        db.add(profile_db)

        session.status = SessionStatus.READY.value
        await db.commit()

        return style_profile

    except Exception as e:
        session.status = SessionStatus.ERROR.value
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/profile", response_model=dict)
async def get_style_profile(
    session_id: str,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the style profile for a session, optionally by version."""
    result = await db.execute(
        select(StyleProfileDB)
        .where(StyleProfileDB.session_id == session_id)
        .order_by(StyleProfileDB.version.desc())
    )
    profiles = result.scalars().all()

    if not profiles:
        raise HTTPException(status_code=404, detail="No style profile found")

    if version is not None:
        profile = next((p for p in profiles if p.version == version), None)
        if not profile:
            raise HTTPException(
                status_code=404, detail=f"Version {version} not found"
            )
    else:
        profile = profiles[0]  # Latest version

    return {
        "version": profile.version,
        "profile": profile.profile_json,
        "created_at": profile.created_at.isoformat(),
        "available_versions": [p.version for p in profiles],
    }
