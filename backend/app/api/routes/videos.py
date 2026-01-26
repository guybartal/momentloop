from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.models.video import Video
from app.schemas.video import GenerateVideoRequest, TransitionVideoRequest, VideoResponse
from app.services.fal_ai import fal_ai_service
from app.services.storage import storage_service

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
        created_at=video.created_at,
    )


async def process_video_generation(
    video_id: UUID,
    image_path: str,
    prompt: str,
    db_url: str,
):
    """Background task to process video generation."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.video import Video

    engine = create_async_engine(db_url)
    async with AsyncSession(engine) as db:
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()

        if not video:
            return

        try:
            video.status = "generating"
            await db.commit()

            # Generate video
            video_bytes = await fal_ai_service.generate_video(
                storage_service.get_full_path(image_path),
                prompt,
                duration=5.0,
            )

            # Save video
            video_path = await storage_service.save_video(
                video_bytes, video.project_id, "scene"
            )

            # Update record
            video.video_path = video_path
            video.duration_seconds = 5.0
            video.status = "ready"

            await db.commit()

        except Exception as e:
            print(f"Video generation failed for video {video_id}: {e}")
            video.status = "failed"
            await db.commit()


@router.post("/photos/{photo_id}/generate-video", response_model=VideoResponse)
async def generate_video_from_photo(
    photo_id: UUID,
    request: GenerateVideoRequest | None = None,
    background_tasks: BackgroundTasks = None,
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

    # Check if video already exists for this photo
    result = await db.execute(
        select(Video).where(
            Video.photo_id == photo_id,
            Video.video_type == "scene",
        )
    )
    existing_video = result.scalar_one_or_none()

    if existing_video:
        # Update existing video
        existing_video.prompt = prompt
        existing_video.status = "pending"
        existing_video.video_path = None
        video = existing_video
    else:
        # Create new video record
        video = Video(
            photo_id=photo_id,
            project_id=photo.project_id,
            video_type="scene",
            prompt=prompt,
            position=photo.position,
            status="pending",
        )
        db.add(video)

    await db.commit()
    await db.refresh(video)

    # Start background generation
    from app.core.config import get_settings

    settings = get_settings()
    background_tasks.add_task(
        process_video_generation,
        video.id,
        image_path,
        prompt,
        settings.database_url,
    )

    return video_to_response(video)


@router.post("/videos/transition", response_model=VideoResponse)
async def generate_transition_video(
    request: TransitionVideoRequest,
    background_tasks: BackgroundTasks,
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
    from app.core.config import get_settings

    settings = get_settings()
    background_tasks.add_task(
        process_video_generation,
        video.id,
        image_path,
        prompt,
        settings.database_url,
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
