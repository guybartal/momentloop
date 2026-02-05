import logging
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.models.video import Export, Video
from app.schemas.export import ExportCreate, ExportResponse, ExportStatusResponse
from app.services.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


def export_to_response(export: Export) -> ExportResponse:
    """Convert an Export model to ExportResponse with URLs."""
    return ExportResponse(
        id=export.id,
        project_id=export.project_id,
        file_path=export.file_path,
        file_url=storage_service.get_url(export.file_path) if export.file_path else None,
        status=export.status,
        created_at=export.created_at,
    )


async def process_export(
    export_id: UUID,
    project_id: UUID,
    db_url: str,
    include_transitions: bool = True,
):
    """Background task to process video export with optional AI-generated transitions."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.video import Export, Video
    from app.services.fal_ai import fal_ai_service
    from app.services.ffmpeg import ffmpeg_service
    from app.services.storage import storage_service

    engine = create_async_engine(db_url)
    async with AsyncSession(engine) as db:
        result = await db.execute(select(Export).where(Export.id == export_id))
        export = result.scalar_one_or_none()

        if not export:
            return

        # Create temp directory for frames
        frames_dir = None

        try:
            export.status = "processing"
            await db.commit()

            # PHASE 1: Get all ready scene videos for the project (ordered by position)
            result = await db.execute(
                select(Video)
                .where(
                    Video.project_id == project_id,
                    Video.status == "ready",
                    Video.video_path.isnot(None),
                    Video.video_type == "scene",
                )
                .order_by(Video.position)
            )
            scene_videos = list(result.scalars().all())

            if not scene_videos:
                export.status = "failed"
                await db.commit()
                return

            # Get full paths for scene videos
            scene_paths = [
                storage_service.get_full_path(video.video_path)
                for video in scene_videos
            ]

            # PHASE 2 & 3: Generate transitions if enabled and we have multiple videos
            transition_paths = []
            if include_transitions and len(scene_videos) > 1:
                # Create temp directory for extracted frames
                frames_dir = Path(tempfile.mkdtemp(prefix=f"frames_{export_id}_"))
                logger.info("Created frames directory: %s", frames_dir)

                for i in range(len(scene_videos) - 1):
                    video_a = scene_videos[i]
                    video_b = scene_videos[i + 1]
                    video_a_path = scene_paths[i]
                    video_b_path = scene_paths[i + 1]

                    logger.info(
                        "Generating transition %d: video %s -> video %s",
                        i + 1,
                        video_a.id,
                        video_b.id,
                    )

                    # Extract last frame from video A
                    frame_a_end = frames_dir / f"scene_{video_a.id}_last.png"
                    await ffmpeg_service.extract_frame(
                        video_a_path, frame_a_end, position="last"
                    )

                    # Extract first frame from video B
                    frame_b_start = frames_dir / f"scene_{video_b.id}_first.png"
                    await ffmpeg_service.extract_frame(
                        video_b_path, frame_b_start, position="first"
                    )

                    # Generate transition video using Kling 2.6
                    transition_prompt = (
                        "Smooth cinematic transition with gentle camera movement, "
                        "seamless morph between scenes"
                    )
                    try:
                        transition_bytes = await fal_ai_service.generate_transition(
                            start_image_path=frame_a_end,
                            end_image_path=frame_b_start,
                            prompt=transition_prompt,
                            duration=5.0,
                        )

                        # Save transition video
                        transition_relative_path = await storage_service.save_video(
                            transition_bytes, project_id, video_type="transition"
                        )
                        transition_path = storage_service.get_full_path(transition_relative_path)
                        transition_paths.append(transition_path)

                        # Create transition video record in database
                        transition_video = Video(
                            project_id=project_id,
                            video_type="transition",
                            video_path=transition_relative_path,
                            source_photo_id=video_a.photo_id,
                            target_photo_id=video_b.photo_id,
                            prompt=transition_prompt,
                            duration_seconds=5.0,
                            position=video_a.position,  # Position after source scene
                            status="ready",
                        )
                        db.add(transition_video)

                        logger.info(
                            "Transition %d generated successfully: %s",
                            i + 1,
                            transition_relative_path,
                        )

                    except Exception as e:
                        logger.error(
                            "Failed to generate transition %d: %s",
                            i + 1,
                            e,
                            exc_info=True,
                        )
                        # Continue without this transition - will use hard cut
                        continue

                await db.commit()

            # PHASE 4: Interleave scene videos and transitions
            final_video_paths = []
            for i, scene_path in enumerate(scene_paths):
                final_video_paths.append(scene_path)
                if i < len(transition_paths):
                    final_video_paths.append(transition_paths[i])

            logger.info(
                "Concatenating %d videos (%d scenes, %d transitions)",
                len(final_video_paths),
                len(scene_paths),
                len(transition_paths),
            )

            # Create output path
            output_path = storage_service.exports_path / str(project_id) / f"export_{export_id}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Concatenate all videos (no FFmpeg crossfade needed - transitions are AI-generated)
            await ffmpeg_service.concatenate_videos(
                final_video_paths,
                output_path,
                transition_duration=0,  # Hard cuts between clips (AI handles transitions)
            )

            # Save relative path
            relative_path = str(output_path.relative_to(storage_service.base_path))
            export.file_path = relative_path
            export.status = "ready"

            await db.commit()
            logger.info("Export completed successfully: %s", relative_path)

        except Exception as e:
            logger.error("Export failed for export %s: %s", export_id, e, exc_info=True)
            export.status = "failed"
            await db.commit()

        finally:
            # Clean up temp frames directory
            if frames_dir and frames_dir.exists():
                shutil.rmtree(frames_dir, ignore_errors=True)
                logger.info("Cleaned up frames directory: %s", frames_dir)


@router.post("/projects/{project_id}/export", response_model=ExportResponse)
async def start_export(
    project_id: UUID,
    request: ExportCreate | None = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start exporting a project video."""
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

    # Check if there are any ready videos
    result = await db.execute(
        select(Video).where(
            Video.project_id == project_id,
            Video.status == "ready",
        )
    )
    videos = result.scalars().all()

    if not videos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ready videos to export",
        )

    # Create export record
    export = Export(
        project_id=project_id,
        status="pending",
    )
    db.add(export)
    await db.commit()
    await db.refresh(export)

    # Start background processing
    from app.core.config import get_settings

    settings = get_settings()
    include_transitions = request.include_transitions if request else True
    background_tasks.add_task(
        process_export,
        export.id,
        project_id,
        settings.database_url,
        include_transitions,
    )

    return export_to_response(export)


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get export details."""
    result = await db.execute(
        select(Export)
        .join(Project)
        .where(Export.id == export_id, Project.user_id == current_user.id)
    )
    export = result.scalar_one_or_none()

    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    return export_to_response(export)


@router.get("/exports/{export_id}/status", response_model=ExportStatusResponse)
async def get_export_status(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check export status."""
    result = await db.execute(
        select(Export)
        .join(Project)
        .where(Export.id == export_id, Project.user_id == current_user.id)
    )
    export = result.scalar_one_or_none()

    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    progress = {
        "pending": 0,
        "processing": 50,
        "ready": 100,
        "failed": 0,
    }.get(export.status, 0)

    return ExportStatusResponse(
        export_id=str(export.id),
        status=export.status,
        file_url=storage_service.get_url(export.file_path) if export.file_path else None,
        progress=progress,
    )


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the exported video."""
    result = await db.execute(
        select(Export)
        .join(Project)
        .where(Export.id == export_id, Project.user_id == current_user.id)
    )
    export = result.scalar_one_or_none()

    if not export:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    if export.status != "ready" or not export.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export not ready",
        )

    file_path = storage_service.get_full_path(export.file_path)

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )

    return FileResponse(
        path=file_path,
        filename=f"momentloop_export_{export_id}.mp4",
        media_type="video/mp4",
    )


@router.get("/projects/{project_id}/exports", response_model=list[ExportResponse])
async def list_project_exports(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all exports for a project."""
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
        select(Export)
        .where(Export.project_id == project_id)
        .order_by(Export.created_at.desc())
    )
    exports = result.scalars().all()

    return [export_to_response(export) for export in exports]
