import logging
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
from app.services.ffmpeg import ffmpeg_service
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
):
    """Background task to process video export."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.video import Export, Video

    engine = create_async_engine(db_url)
    async with AsyncSession(engine) as db:
        result = await db.execute(select(Export).where(Export.id == export_id))
        export = result.scalar_one_or_none()

        if not export:
            return

        try:
            export.status = "processing"
            await db.commit()

            # Get all ready videos for the project
            result = await db.execute(
                select(Video)
                .where(
                    Video.project_id == project_id,
                    Video.status == "ready",
                    Video.video_path.isnot(None),
                )
                .order_by(Video.position, Video.video_type.desc())  # transitions after scenes
            )
            videos = result.scalars().all()

            if not videos:
                export.status = "failed"
                await db.commit()
                return

            # Get full paths for all videos
            video_paths = [
                storage_service.get_full_path(video.video_path)
                for video in videos
            ]

            # Create output path
            output_path = storage_service.exports_path / str(project_id) / f"export_{export_id}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Concatenate videos
            await ffmpeg_service.concatenate_videos(
                video_paths,
                output_path,
                transition_duration=0,  # Use simple concatenation
            )

            # Save relative path
            relative_path = str(output_path.relative_to(storage_service.base_path))
            export.file_path = relative_path
            export.status = "ready"

            await db.commit()

        except Exception as e:
            logger.error("Export failed for export %s: %s", export_id, e, exc_info=True)
            export.status = "failed"
            await db.commit()


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
    background_tasks.add_task(
        process_export,
        export.id,
        project_id,
        settings.database_url,
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
