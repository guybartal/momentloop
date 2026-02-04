import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.concurrency import get_semaphore_manager
from app.core.database import get_db, background_session_maker
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.models.video import Video
from app.schemas.video import GenerateVideoRequest, SelectVideoRequest, TransitionVideoRequest, VideoResponse
from app.services.fal_ai import fal_ai_service
from app.services.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


def video_to_response(video: Video) -> VideoResponse:
    """Convert a Video model to VideoResponse with URLs."""
    return VideoResponse(
        id=video.id,
        photo_id=video.photo_id,
        project_id=video.project_id,
        video_path=video.video_path,
        video_url=storage_service.get_url(video.video_path) if video.video_path else None,
        video_type=video.video_type,
        source_photo_id=video.source_photo_id,
        target_photo_id=video.target_photo_id,
        prompt=video.prompt,
        duration_seconds=video.duration_seconds,
        position=video.position,
        status=video.status,
        is_selected=video.is_selected,
        created_at=video.created_at,
    )


async def update_video_status(video_id: UUID, status_value: str):
    """Update a video's status using background session."""
    async with background_session_maker() as db:
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video:
            video.status = status_value
            await db.commit()


async def process_video_generation(
    video_id: UUID,
    image_path: str,
    prompt: str,
    project_id: UUID,
    photo_id: UUID | None = None,
):
    """Background task to process video generation."""
    semaphore_manager = get_semaphore_manager()
    async with semaphore_manager.video_generation:
        logger.info("Starting video generation for video %s", video_id)

        # Update status to generating
        await update_video_status(video_id, "generating")

        try:
            # Generate video
            video_bytes = await fal_ai_service.generate_video(
                storage_service.get_full_path(image_path),
                prompt,
                duration=5.0,
            )
            logger.info("Video generation complete for %s, got %d bytes", video_id, len(video_bytes))

            # Save video
            video_path = await storage_service.save_video(
                video_bytes, project_id, "scene"
            )
            logger.debug("Saved video to: %s", video_path)

            # Update record and mark as selected (deselect others for same photo)
            async with background_session_maker() as db:
                # Deselect other videos for this photo
                if photo_id:
                    result = await db.execute(
                        select(Video).where(
                            Video.photo_id == photo_id,
                            Video.video_type == "scene",
                        )
                    )
                    other_videos = result.scalars().all()
                    for v in other_videos:
                        v.is_selected = False

                result = await db.execute(select(Video).where(Video.id == video_id))
                video = result.scalar_one_or_none()
                if video:
                    video.video_path = video_path
                    video.duration_seconds = 5.0
                    video.status = "ready"
                    video.is_selected = True
                    await db.commit()

            logger.info("Video %s status updated to 'ready'", video_id)

        except Exception as e:
            logger.error("Video generation failed for video %s: %s", video_id, e, exc_info=True)
            await update_video_status(video_id, "failed")


@router.post("/photos/{photo_id}/generate-video", response_model=VideoResponse)
async def generate_video_from_photo(
    photo_id: UUID,
    request: GenerateVideoRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a video from a styled photo."""
    # Get photo with ownership check
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

    # Determine which image to use
    image_path = photo.styled_path or photo.original_path

    # Determine prompt
    prompt = (request.prompt if request and request.prompt else None) or photo.animation_prompt
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No animation prompt available. Generate or provide one.",
        )

    # Deselect all existing videos for this photo
    result = await db.execute(
        select(Video).where(
            Video.photo_id == photo_id,
            Video.video_type == "scene",
        )
    )
    existing_videos = result.scalars().all()
    for v in existing_videos:
        v.is_selected = False

    # Create new video record (always create new, don't update existing)
    video = Video(
        photo_id=photo_id,
        project_id=photo.project_id,
        video_type="scene",
        prompt=prompt,
        position=photo.position,
        status="pending",
        is_selected=False,  # Will be set to True when generation completes
    )
    db.add(video)

    await db.commit()
    await db.refresh(video)

    # Start background generation using asyncio.create_task
    asyncio.create_task(
        process_video_generation(
            video.id,
            image_path,
            prompt,
            photo.project_id,
            photo_id,
        )
    )

    return video_to_response(video)


@router.post("/videos/transition", response_model=VideoResponse)
async def generate_transition_video(
    request: TransitionVideoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a transition video between two photos."""
    # Get source photo
    result = await db.execute(
        select(Photo)
        .join(Project)
        .where(Photo.id == request.source_photo_id, Project.user_id == current_user.id)
    )
    source_photo = result.scalar_one_or_none()

    if not source_photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source photo not found",
        )

    # Get target photo
    result = await db.execute(
        select(Photo)
        .join(Project)
        .where(Photo.id == request.target_photo_id, Project.user_id == current_user.id)
    )
    target_photo = result.scalar_one_or_none()

    if not target_photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target photo not found",
        )

    # Ensure photos are in same project
    if source_photo.project_id != target_photo.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photos must be in the same project",
        )

    # Create transition prompt
    prompt = request.prompt or "Smooth cinematic transition with gentle camera movement"

    # Create video record
    video = Video(
        project_id=source_photo.project_id,
        video_type="transition",
        source_photo_id=request.source_photo_id,
        target_photo_id=request.target_photo_id,
        prompt=prompt,
        position=source_photo.position,  # Transition follows source
        status="pending",
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)

    # Use source photo's styled image for transition
    image_path = source_photo.styled_path or source_photo.original_path

    # Start background generation
    asyncio.create_task(
        process_video_generation(
            video.id,
            image_path,
            prompt,
            source_photo.project_id,
        )
    )

    return video_to_response(video)


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific video."""
    result = await db.execute(
        select(Video)
        .join(Project)
        .where(Video.id == video_id, Project.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return video_to_response(video)


@router.get("/videos/{video_id}/status")
async def get_video_status(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check the generation status of a video."""
    result = await db.execute(
        select(Video)
        .join(Project)
        .where(Video.id == video_id, Project.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return {
        "video_id": str(video.id),
        "status": video.status,
        "video_url": storage_service.get_url(video.video_path) if video.video_path else None,
    }


@router.get("/projects/{project_id}/videos", response_model=list[VideoResponse])
async def list_project_videos(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all videos in a project."""
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
        select(Video)
        .where(Video.project_id == project_id)
        .order_by(Video.position, Video.video_type)
    )
    videos = result.scalars().all()

    return [video_to_response(video) for video in videos]


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a video."""
    result = await db.execute(
        select(Video)
        .join(Project)
        .where(Video.id == video_id, Project.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Delete file
    if video.video_path:
        await storage_service.delete_file(video.video_path)

    await db.delete(video)
    await db.commit()


@router.get("/photos/{photo_id}/videos", response_model=list[VideoResponse])
async def list_photo_videos(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all video variants for a photo."""
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

    # Get all videos for this photo
    result = await db.execute(
        select(Video)
        .where(Video.photo_id == photo_id, Video.video_type == "scene")
        .order_by(Video.created_at.desc())
    )
    videos = result.scalars().all()

    return [video_to_response(video) for video in videos]


@router.post("/photos/{photo_id}/videos/select", response_model=VideoResponse)
async def select_photo_video(
    photo_id: UUID,
    request: SelectVideoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Select a specific video as the active one for a photo."""
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

    # Verify video belongs to this photo
    result = await db.execute(
        select(Video).where(
            Video.id == request.video_id,
            Video.photo_id == photo_id,
        )
    )
    selected_video = result.scalar_one_or_none()

    if not selected_video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Deselect all videos for this photo
    result = await db.execute(
        select(Video).where(Video.photo_id == photo_id)
    )
    all_videos = result.scalars().all()
    for v in all_videos:
        v.is_selected = False

    # Select the chosen video
    selected_video.is_selected = True

    await db.commit()

    return video_to_response(selected_video)
