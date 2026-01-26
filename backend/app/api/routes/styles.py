import asyncio
import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.styled_variant import StyledVariant
from app.models.user import User
from app.services.imagen import imagen_service
from app.services.storage import storage_service

router = APIRouter()

VALID_STYLES = {"ghibli", "lego", "minecraft", "simpsons"}


class StyleRequest(BaseModel):
    style: str


class SelectVariantRequest(BaseModel):
    variant_id: UUID


async def process_style_transfer_for_photo(
    photo_id: UUID,
    style: str,
    db_url: str,
    save_as_variant: bool = True,
):
    """Background task to process style transfer for a single photo."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.photo import Photo
    from app.models.styled_variant import StyledVariant

    print(f"Starting style transfer for photo {photo_id} with style {style}")

    engine = create_async_engine(db_url)

    # Get photo path
    async with AsyncSession(engine) as db:
        result = await db.execute(
            select(Photo.original_path).where(Photo.id == photo_id)
        )
        row = result.first()
        if not row:
            print(f"Photo {photo_id} not found")
            await engine.dispose()
            return
        original_path = row[0]

    # Do style transfer outside session
    try:
        full_path = storage_service.get_full_path(original_path)
        print(f"Processing image at: {full_path}")

        # Apply style transfer
        styled_bytes = await imagen_service.apply_style(full_path, style)
        print(f"Style transfer complete, got {len(styled_bytes)} bytes")

        # Save the styled image
        styled_path = await storage_service.save_styled(styled_bytes, original_path)
        print(f"Saved styled image to: {styled_path}")

        # Update photo record and create variant
        async with AsyncSession(engine) as db:
            result = await db.execute(select(Photo).where(Photo.id == photo_id))
            photo = result.scalar_one_or_none()
            if photo:
                # Create a new variant
                if save_as_variant:
                    # Deselect all existing variants for this photo
                    await db.execute(
                        select(StyledVariant).where(StyledVariant.photo_id == photo_id)
                    )
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

                # Update photo's styled_path to the new one
                photo.styled_path = styled_path
                photo.status = "styled"
                await db.commit()
                print(f"Photo {photo_id} status updated to 'styled'")

    except Exception as e:
        print(f"Style transfer failed for photo {photo_id}: {e}")
        traceback.print_exc()
        async with AsyncSession(engine) as db:
            result = await db.execute(select(Photo).where(Photo.id == photo_id))
            photo = result.scalar_one_or_none()
            if photo:
                photo.status = "uploaded"  # Reset status on failure
                await db.commit()

    await engine.dispose()


async def process_project_style_transfer(
    project_id: UUID,
    style: str,
    db_url: str,
):
    """Background task to process style transfer for all photos in a project."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.photo import Photo
    from app.models.project import Project
    from app.models.styled_variant import StyledVariant

    print(f"Starting style transfer for project {project_id} with style {style}")

    engine = create_async_engine(db_url)

    # First, get all photo IDs and paths
    async with AsyncSession(engine) as db:
        result = await db.execute(
            select(Photo.id, Photo.original_path)
            .where(Photo.project_id == project_id)
            .order_by(Photo.position)
        )
        photo_data = [(row[0], row[1]) for row in result.fetchall()]
        print(f"Found {len(photo_data)} photos to process")

    # Process each photo
    for photo_id, original_path in photo_data:
        # Update status to styling
        async with AsyncSession(engine) as db:
            try:
                result = await db.execute(select(Photo).where(Photo.id == photo_id))
                photo = result.scalar_one_or_none()
                if photo:
                    photo.status = "styling"
                    await db.commit()
            except Exception as e:
                print(f"Failed to update photo {photo_id} status: {e}")
                continue

        # Do the style transfer (outside session context)
        try:
            full_path = storage_service.get_full_path(original_path)
            print(f"Processing image at: {full_path}")

            # Apply style transfer
            styled_bytes = await imagen_service.apply_style(full_path, style)
            print(f"Style transfer complete for photo {photo_id}, got {len(styled_bytes)} bytes")

            # Save the styled image
            styled_path = await storage_service.save_styled(styled_bytes, original_path)
            print(f"Saved styled image to: {styled_path}")

            # Update photo with styled path and create variant
            async with AsyncSession(engine) as db:
                result = await db.execute(select(Photo).where(Photo.id == photo_id))
                photo = result.scalar_one_or_none()
                if photo:
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
                    print(f"Photo {photo_id} status updated to 'styled'")

        except Exception as e:
            print(f"Style transfer failed for photo {photo_id}: {e}")
            traceback.print_exc()
            # Reset status on failure
            async with AsyncSession(engine) as db:
                result = await db.execute(select(Photo).where(Photo.id == photo_id))
                photo = result.scalar_one_or_none()
                if photo:
                    photo.status = "uploaded"
                    await db.commit()

    # Update project status
    async with AsyncSession(engine) as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project:
            project.status = "draft"  # Back to draft after styling complete
            await db.commit()

    await engine.dispose()
    print(f"Project {project_id} style transfer complete")


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

    # Start background task using asyncio
    from app.core.config import get_settings

    settings = get_settings()
    asyncio.create_task(
        process_project_style_transfer(
            project_id,
            style_request.style,
            settings.database_url,
        )
    )

    return {"message": "Style transfer started", "project_id": str(project_id)}


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

    return {
        "project_id": str(project.id),
        "style": project.style,
        "project_status": project.status,
        "total_photos": total,
        "styled_count": styled,
        "styling_count": styling,
        "photos": photo_statuses,
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
