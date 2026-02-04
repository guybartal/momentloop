import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.concurrency import get_semaphore_manager
from app.core.database import get_db, background_session_maker
from app.models.photo import Photo
from app.models.project import Project
from app.models.styled_variant import StyledVariant
from app.models.user import User
from app.services.imagen import imagen_service
from app.services.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STYLES = {"ghibli", "lego", "minecraft", "simpsons"}


class StyleRequest(BaseModel):
    style: str


class SelectVariantRequest(BaseModel):
    variant_id: UUID


async def process_single_photo_style(
    photo_id: UUID,
    original_path: str,
    style: str,
    custom_prompt: str | None = None,
) -> tuple[UUID, bool, str | None]:
    """
    Process style transfer for a single photo.
    Returns (photo_id, success, styled_path or error message)
    """
    semaphore_manager = get_semaphore_manager()
    async with semaphore_manager.style_transfer:
        try:
            full_path = storage_service.get_full_path(original_path)
            logger.debug("Processing image at: %s", full_path)

            # Apply style transfer with optional custom prompt
            styled_bytes = await imagen_service.apply_style(full_path, style, custom_prompt)
            logger.debug("Style transfer complete for photo %s, got %d bytes", photo_id, len(styled_bytes))

            # Save the styled image
            styled_path = await storage_service.save_styled(styled_bytes, original_path)
            logger.debug("Saved styled image to: %s", styled_path)

            return (photo_id, True, styled_path)

        except Exception as e:
            logger.error("Style transfer failed for photo %s: %s", photo_id, e, exc_info=True)
            return (photo_id, False, str(e))


async def update_photo_status(photo_id: UUID, status_value: str):
    """Update a photo's status using background session."""
    async with background_session_maker() as db:
        result = await db.execute(select(Photo).where(Photo.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo:
            photo.status = status_value
            await db.commit()


async def save_photo_result(
    photo_id: UUID,
    styled_path: str,
    style: str,
    save_as_variant: bool = True,
):
    """Save the styled result for a photo."""
    async with background_session_maker() as db:
        result = await db.execute(select(Photo).where(Photo.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo:
            if save_as_variant:
                # Deselect existing variants
                existing_variants = (await db.execute(
                    select(StyledVariant).where(StyledVariant.photo_id == photo_id)
                )).scalars().all()
                for v in existing_variants:
                    v.is_selected = False

                # Create new variant as selected
                variant = StyledVariant(
                    photo_id=photo_id,
                    styled_path=styled_path,
                    style=style,
                    is_selected=True,
                )
                db.add(variant)

            photo.styled_path = styled_path
            photo.status = "styled"
            await db.commit()
            logger.info("Photo %s status updated to 'styled'", photo_id)


async def process_style_transfer_for_photo(
    photo_id: UUID,
    style: str,
    save_as_variant: bool = True,
    custom_prompt: str | None = None,
):
    """Background task to process style transfer for a single photo."""
    logger.info("Starting style transfer for photo %s with style %s", photo_id, style)

    # Get photo path
    async with background_session_maker() as db:
        result = await db.execute(
            select(Photo.original_path).where(Photo.id == photo_id)
        )
        row = result.first()
        if not row:
            logger.warning("Photo %s not found", photo_id)
            return
        original_path = row[0]

    # Update status to styling
    await update_photo_status(photo_id, "styling")

    # Process the photo
    photo_id, success, result = await process_single_photo_style(
        photo_id, original_path, style, custom_prompt
    )

    if success:
        await save_photo_result(photo_id, result, style, save_as_variant)
    else:
        await update_photo_status(photo_id, "uploaded")


async def process_project_style_transfer(
    project_id: UUID,
    style: str,
    custom_prompt: str | None = None,
):
    """Background task to process style transfer for all photos in a project concurrently."""
    logger.info("Starting style transfer for project %s with style %s", project_id, style)

    # Get all photo IDs and paths
    async with background_session_maker() as db:
        result = await db.execute(
            select(Photo.id, Photo.original_path)
            .where(Photo.project_id == project_id)
            .order_by(Photo.position)
        )
        photo_data = [(row[0], row[1]) for row in result.fetchall()]
        logger.info("Found %d photos to process", len(photo_data))

    if not photo_data:
        return

    # Mark all photos as styling
    async with background_session_maker() as db:
        for photo_id, _ in photo_data:
            result = await db.execute(select(Photo).where(Photo.id == photo_id))
            photo = result.scalar_one_or_none()
            if photo:
                photo.status = "styling"
        await db.commit()

    # Process all photos concurrently with semaphore limiting
    tasks = [
        process_single_photo_style(photo_id, original_path, style, custom_prompt)
        for photo_id, original_path in photo_data
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Save results
    for result in results:
        if isinstance(result, Exception):
            logger.error("Task failed with exception: %s", result)
            continue

        photo_id, success, styled_path_or_error = result
        if success:
            await save_photo_result(photo_id, styled_path_or_error, style, True)
        else:
            await update_photo_status(photo_id, "uploaded")

    # Update project status
    async with background_session_maker() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project:
            project.status = "draft"
            await db.commit()

    logger.info("Project %s style transfer complete", project_id)


@router.post("/projects/{project_id}/stylize")
async def stylize_project(
    project_id: UUID,
    style_request: StyleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a style to all photos in a project."""
    if style_request.style not in VALID_STYLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid style. Must be one of: {VALID_STYLES}",
        )

    # Verify project ownership
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Update project style and status
    project.style = style_request.style
    project.status = "processing"
    await db.commit()

    # Start background task using asyncio (use project's custom prompt if set)
    asyncio.create_task(
        process_project_style_transfer(
            project_id,
            style_request.style,
            project.style_prompt,
        )
    )

    return {"message": "Style transfer started", "project_id": str(project_id)}


@router.post("/photos/{photo_id}/regenerate")
async def regenerate_photo_style(
    photo_id: UUID,
    style_request: StyleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate style for a single photo."""
    if style_request.style not in VALID_STYLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid style. Must be one of: {VALID_STYLES}",
        )

    # Verify ownership and get project for custom prompt
    result = await db.execute(
        select(Photo, Project)
        .join(Project)
        .where(Photo.id == photo_id, Project.user_id == current_user.id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    photo, project = row

    # Update status
    photo.status = "styling"
    await db.commit()

    # Start background task with project's custom prompt
    asyncio.create_task(
        process_style_transfer_for_photo(
            photo_id,
            style_request.style,
            save_as_variant=True,
            custom_prompt=project.style_prompt,
        )
    )

    return {"message": "Regeneration started", "photo_id": str(photo_id)}


@router.get("/projects/{project_id}/style-status")
async def get_project_style_status(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check the style transfer status of a project."""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get photo statuses
    result = await db.execute(
        select(Photo).where(Photo.project_id == project_id).order_by(Photo.position)
    )
    photos = result.scalars().all()

    photo_statuses = [
        {
            "photo_id": str(photo.id),
            "status": photo.status,
            "styled_url": storage_service.get_url(photo.styled_path) if photo.styled_path else None,
        }
        for photo in photos
    ]

    # Calculate overall progress
    total = len(photos)
    styled = sum(1 for p in photos if p.status == "styled")
    styling = sum(1 for p in photos if p.status == "styling")
    uploaded = sum(1 for p in photos if p.status == "uploaded")

    # Auto-fix stuck project status: if no photos are styling but project is still "processing"
    if project.status == "processing" and styling == 0:
        project.status = "draft"
        await db.commit()

    return {
        "project_id": str(project.id),
        "style": project.style,
        "project_status": project.status,
        "total_photos": total,
        "styled_count": styled,
        "styling_count": styling,
        "uploaded_count": uploaded,
        "photos": photo_statuses,
    }


@router.post("/projects/{project_id}/reset-stuck")
async def reset_stuck_photos(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset photos stuck in 'styling' status back to 'uploaded'."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Reset stuck photos
    result = await db.execute(
        select(Photo).where(
            Photo.project_id == project_id,
            Photo.status == "styling",
        )
    )
    stuck_photos = result.scalars().all()

    reset_count = 0
    for photo in stuck_photos:
        photo.status = "uploaded"
        reset_count += 1

    # Also reset project status if it was processing
    if project.status == "processing":
        project.status = "draft"

    await db.commit()

    return {
        "reset_count": reset_count,
        "project_status": project.status,
    }


@router.get("/photos/{photo_id}/variants")
async def get_photo_variants(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all styled variants for a photo."""
    # Verify ownership
    result = await db.execute(
        select(Photo)
        .join(Project)
        .where(Photo.id == photo_id, Project.user_id == current_user.id)
    )
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    # Get all variants
    result = await db.execute(
        select(StyledVariant)
        .where(StyledVariant.photo_id == photo_id)
        .order_by(StyledVariant.created_at.desc())
    )
    variants = result.scalars().all()

    return {
        "photo_id": str(photo_id),
        "variants": [
            {
                "id": str(v.id),
                "styled_url": storage_service.get_url(v.styled_path),
                "style": v.style,
                "is_selected": v.is_selected,
                "created_at": v.created_at.isoformat(),
            }
            for v in variants
        ],
    }


@router.post("/photos/{photo_id}/variants/select")
async def select_photo_variant(
    photo_id: UUID,
    request: SelectVariantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Select a specific variant as the active styled image for a photo."""
    # Verify ownership
    result = await db.execute(
        select(Photo)
        .join(Project)
        .where(Photo.id == photo_id, Project.user_id == current_user.id)
    )
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    # Verify variant belongs to this photo
    result = await db.execute(
        select(StyledVariant).where(
            StyledVariant.id == request.variant_id,
            StyledVariant.photo_id == photo_id,
        )
    )
    selected_variant = result.scalar_one_or_none()

    if not selected_variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found",
        )

    # Deselect all variants for this photo
    result = await db.execute(
        select(StyledVariant).where(StyledVariant.photo_id == photo_id)
    )
    all_variants = result.scalars().all()
    for v in all_variants:
        v.is_selected = False

    # Select the chosen variant
    selected_variant.is_selected = True

    # Update photo's styled_path
    photo.styled_path = selected_variant.styled_path

    await db.commit()

    return {
        "message": "Variant selected",
        "photo_id": str(photo_id),
        "variant_id": str(request.variant_id),
        "styled_url": storage_service.get_url(selected_variant.styled_path),
    }
