from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.schemas.photo import PhotoReorderRequest, PhotoResponse, PhotoUpdate
from app.services.storage import storage_service
from app.services.prompt_generator import prompt_generator_service

router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


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

    return [photo_to_response(photo) for photo in uploaded_photos]


@router.get("/projects/{project_id}/photos", response_model=list[PhotoResponse])
async def list_photos(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all photos in a project."""
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

    result = await db.execute(
        select(Photo)
        .where(Photo.project_id == project_id)
        .order_by(Photo.position)
    )
    photos = result.scalars().all()

    return [photo_to_response(photo) for photo in photos]


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

    # Update positions
    for i, photo_id in enumerate(reorder_data.photo_ids):
        if photo_id in photos:
            photos[photo_id].position = i

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
    feedback: str | None = None,
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
        image_path, current_prompt, feedback
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
    from app.core.config import get_settings
    from app.api.routes.styles import process_style_transfer_for_photo

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
