import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job import Job
from app.models.project import Project
from app.models.user import User
from app.schemas.job import JobCreate, JobResponse

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_JOB_TYPES = {"style_transfer", "prompt_generation", "video_generation", "export"}


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    project_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List jobs for the current user, optionally filtered by project and/or status."""
    query = select(Job).where(Job.user_id == current_user.id)

    if project_id:
        query = query.where(Job.project_id == project_id)
    if status_filter:
        query = query.where(Job.status == status_filter)

    query = query.order_by(Job.created_at.desc()).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return [JobResponse.model_validate(job) for job in jobs]


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new job record."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == job_data.project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if job_data.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job type. Must be one of: {VALID_JOB_TYPES}",
        )

    job = Job(
        user_id=current_user.id,
        project_id=job_data.project_id,
        job_type=job_data.job_type,
        description=job_data.description,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.patch("/jobs/{job_id}/complete", response_model=JobResponse)
async def complete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a job as completed."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.status = "completed"
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.patch("/jobs/{job_id}/fail", response_model=JobResponse)
async def fail_job(
    job_id: UUID,
    error: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a job as failed."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)

    return JobResponse.model_validate(job)


@router.delete("/jobs/notifications", status_code=status.HTTP_204_NO_CONTENT)
async def clear_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all completed/failed jobs for the current user."""
    result = await db.execute(
        select(Job).where(
            Job.user_id == current_user.id,
            Job.status.in_(["completed", "failed"]),
        )
    )
    jobs = result.scalars().all()
    for job in jobs:
        await db.delete(job)
    await db.commit()


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_notification(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single completed/failed job notification."""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == current_user.id,
            Job.status.in_(["completed", "failed"]),
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or still running",
        )

    await db.delete(job)
    await db.commit()
