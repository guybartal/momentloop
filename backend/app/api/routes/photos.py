import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.concurrency import get_semaphore_manager
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.models.video import Video
from app.schemas.pagination import PaginatedResponse
from app.schemas.photo import (
    PhotoReorderRequest,
    PhotoResponse,
    PhotoUpdate,
    RegeneratePromptRequest,
)
from app.services.prompt_generator import prompt_generator_service
from app.services.storage import storage_service

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def generate_prompt_for_photo(photo_id: UUID, database_url: str, max_retries: int = 3):
    """Background task to generate video prompt for a photo."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    logger.info("Starting prompt generation task for photo %s", photo_id)

    # Use semaphore to limit concurrent AI API calls
    semaphore_manager = get_semaphore_manager()
    async with semaphore_manager.prompt_generation:
        logger.info("Acquired semaphore for photo %s", photo_id)

        engine = create_async_engine(database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        try:
            async with async_session() as db:
                result = await db.execute(select(Photo).where(Photo.id == photo_id))
                photo = result.scalar_one_or_none()

                if not photo:
                    logger.warning("Photo %s not found for prompt generation", photo_id)
                    return

                # Skip if prompt already exists and status is completed
                if photo.animation_prompt and photo.prompt_generation_status == "completed":
                    logger.info("Photo %s already has a prompt, skipping", photo_id)
                    return

                # Set status to generating
                photo.prompt_generation_status = "generating"
                await db.commit()

                # Use original image for prompt generation
                image_path = storage_service.get_full_path(photo.original_path)
                logger.info("Generating prompt for photo %s using image: %s", photo_id, image_path)

                # Retry logic for rate limiting
                last_error = None
                for attempt in range(max_retries):
                    try:
                        prompt = await prompt_generator_service.generate_video_prompt(image_path)
                        photo.animation_prompt = prompt
                        photo.prompt_generation_status = "completed"
                        await db.commit()
                        logger.info("Generated video prompt for photo %s: %s...", photo_id, prompt[:50])
                        return
                    except Exception as e:
                        last_error = e
                        error_str = str(e)
                        # Check for rate limiting errors
                        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                            wait_time = (2 ** attempt) * 2  # 2, 4, 8 seconds
                            logger.warning(
                                "Rate limited on attempt %d/%d for photo %s, waiting %ds before retry",
                                attempt + 1, max_retries, photo_id, wait_time
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            # Non-rate-limit error, don't retry
                            break

                # All retries failed
                logger.error(
                    "Failed to generate prompt for photo %s after %d attempts: %s",
                    photo_id, max_retries, last_error
                )
                photo.prompt_generation_status = "failed"
                await db.commit()

        except Exception as e:
            logger.error("Database error in prompt generation for %s: %s", photo_id, e, exc_info=True)
            # Try to mark as failed
            try:
                async with async_session() as db:
                    result = await db.execute(select(Photo).where(Photo.id == photo_id))
                    photo = result.scalar_one_or_none()
                    if photo:
                        photo.prompt_generation_status = "failed"
                        await db.commit()
            except Exception as inner_e:
                logger.error("Failed to mark photo %s as failed: %s", photo_id, inner_e)
        finally:
            await engine.dispose()


def photo_to_response(photo: Photo) -> PhotoResponse:
    """Convert a Photo model to PhotoResponse with URLs."""
    return PhotoResponse(
        id=photo.id,
        project_id=photo.project_id,
        original_path=photo.original_path,
        original_url=storage_service.get_url(photo.original_path),
        styled_path=photo.styled_path,
        styled_url=storage_service.get_url(photo.styled_path) if photo.styled_path else None,
        animation_prompt=photo.animation_prompt,
        prompt_generation_status=photo.prompt_generation_status,
        position=photo.position,
        status=photo.status,
        created_at=photo.created_at,
    )


@router.post("/projects/{project_id}/photos", response_model=list[PhotoResponse])
async def upload_photos(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload multiple photos to a project."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get current max position
    result = await db.execute(
        select(Photo.position)
        .where(Photo.project_id == project_id)
        .order_by(Photo.position.desc())
        .limit(1)
    )
    max_position = result.scalar() or -1

    uploaded_photos = []

    for i, file in enumerate(files):
        # Validate file extension
        ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {ext} not allowed. Allowed: {ALLOWED_EXTENSIONS}",
            )

        # Read file content
        content = await file.read()

        # Validate file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} exceeds maximum size of {MAX_FILE_SIZE // 1024 // 1024}MB",
            )

        # Save file
        relative_path = await storage_service.save_upload(
            content, file.filename, project_id
        )

        # Create photo record
        photo = Photo(
            project_id=project_id,
            original_path=relative_path,
            position=max_position + i + 1,
            status="uploaded",
        )
        db.add(photo)
        uploaded_photos.append(photo)

    await db.commit()

    # Refresh all photos to get IDs
    for photo in uploaded_photos:
        await db.refresh(photo)

    # Start background prompt generation for each photo
    from app.core.config import get_settings
    settings = get_settings()
    for photo in uploaded_photos:
        asyncio.create_task(
            generate_prompt_for_photo(photo.id, settings.database_url)
        )

    return [photo_to_response(photo) for photo in uploaded_photos]


@router.get("/projects/{project_id}/photos", response_model=PaginatedResponse[PhotoResponse])
async def list_photos(
    project_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all photos in a project with pagination."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get total count
    count_result = await db.execute(
        select(func.count(Photo.id)).where(Photo.project_id == project_id)
    )
    total = count_result.scalar() or 0

    # Get paginated photos
    result = await db.execute(
        select(Photo)
        .options(selectinload(Photo.variants))
        .where(Photo.project_id == project_id)
        .order_by(Photo.position)
        .offset(skip)
        .limit(limit)
    )
    photos = result.scalars().all()

    return PaginatedResponse(
        items=[photo_to_response(photo) for photo in photos],
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + len(photos) < total,
    )


@router.get("/photos/{photo_id}", response_model=PhotoResponse)
async def get_photo(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific photo."""
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

    return photo_to_response(photo)


@router.put("/photos/{photo_id}", response_model=PhotoResponse)
async def update_photo(
    photo_id: UUID,
    photo_data: PhotoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a photo."""
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

    if photo_data.animation_prompt is not None:
        photo.animation_prompt = photo_data.animation_prompt
    if photo_data.position is not None:
        photo.position = photo_data.position

    await db.commit()
    await db.refresh(photo)

    return photo_to_response(photo)


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a photo."""
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

    # Delete files
    await storage_service.delete_file(photo.original_path)
    if photo.styled_path:
        await storage_service.delete_file(photo.styled_path)

    await db.delete(photo)
    await db.commit()


@router.put("/projects/{project_id}/photos/reorder", response_model=list[PhotoResponse])
async def reorder_photos(
    project_id: UUID,
    reorder_data: PhotoReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder photos in a project."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get all photos for the project
    result = await db.execute(
        select(Photo).where(Photo.project_id == project_id)
    )
    photos = {photo.id: photo for photo in result.scalars().all()}

    # Update photo positions
    for i, photo_id in enumerate(reorder_data.photo_ids):
        if photo_id in photos:
            photos[photo_id].position = i

    # Also update video positions to match their associated photos
    result = await db.execute(
        select(Video).where(
            Video.project_id == project_id,
            Video.photo_id.isnot(None),
        )
    )
    videos = result.scalars().all()
    for video in videos:
        if video.photo_id in photos:
            video.position = photos[video.photo_id].position

    await db.commit()

    # Return photos in new order
    ordered_photos = sorted(photos.values(), key=lambda p: p.position)
    return [photo_to_response(photo) for photo in ordered_photos]


@router.post("/photos/{photo_id}/generate-prompt")
async def generate_animation_prompt(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an animation prompt for a photo."""
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

    # Use styled image if available, otherwise original
    image_path = storage_service.get_full_path(
        photo.styled_path if photo.styled_path else photo.original_path
    )

    # Generate prompt
    prompt = await prompt_generator_service.generate_prompt(image_path, None)

    # Save to database
    photo.animation_prompt = prompt
    await db.commit()
    await db.refresh(photo)

    return {"photo_id": str(photo.id), "animation_prompt": prompt}


@router.post("/photos/{photo_id}/regenerate-prompt")
async def regenerate_animation_prompt(
    photo_id: UUID,
    request: RegeneratePromptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate an animation prompt with optional feedback."""
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

    # Use styled image if available, otherwise original
    image_path = storage_service.get_full_path(
        photo.styled_path if photo.styled_path else photo.original_path
    )

    current_prompt = photo.animation_prompt or ""

    # Regenerate prompt
    prompt = await prompt_generator_service.regenerate_prompt(
        image_path, current_prompt, request.feedback
    )

    # Save to database
    photo.animation_prompt = prompt
    await db.commit()
    await db.refresh(photo)

    return {"photo_id": str(photo.id), "animation_prompt": prompt}


@router.post("/photos/{photo_id}/regenerate")
async def regenerate_styled_photo(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate styled image for a single photo."""
    import asyncio

    from app.api.routes.styles import process_style_transfer_for_photo
    from app.core.config import get_settings

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

    # Get project to get the style
    result = await db.execute(
        select(Project).where(Project.id == photo.project_id)
    )
    project = result.scalar_one_or_none()

    if not project or not project.style:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no style selected",
        )

    # Update photo status
    photo.status = "styling"
    await db.commit()

    # Start background task
    settings = get_settings()
    asyncio.create_task(
        process_style_transfer_for_photo(
            photo_id,
            project.style,
            settings.database_url,
        )
    )

    return {"message": "Regeneration started", "photo_id": str(photo_id)}
