import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import background_session_maker
from app.models.job import Job
from app.models.photo import Photo
from app.models.project import Project

logger = logging.getLogger(__name__)


async def reset_orphaned_jobs():
    """Mark any jobs still 'running' from a previous server shutdown as failed."""
    try:
        async with background_session_maker() as db:
            result = await db.execute(select(Job).where(Job.status == "running"))
            orphaned = result.scalars().all()
            now = datetime.now(timezone.utc)
            for job in orphaned:
                job.status = "failed"
                job.error = "Server restarted while job was running"
                job.completed_at = now
            if orphaned:
                await db.commit()
                logger.info("Reset %d orphaned jobs from previous run", len(orphaned))
    except Exception as e:
        logger.error("Failed to reset orphaned jobs: %s", e, exc_info=True)


async def detect_and_reset_stuck_jobs():
    """Periodically check for jobs stuck in 'running' status and mark them as failed."""
    settings = get_settings()
    default_timeout = timedelta(minutes=settings.stuck_job_timeout_minutes)
    export_timeout = timedelta(minutes=settings.stuck_export_timeout_minutes)

    while True:
        try:
            async with background_session_maker() as db:
                now = datetime.now(timezone.utc)

                # Find stuck non-export jobs
                default_cutoff = now - default_timeout
                result = await db.execute(
                    select(Job).where(
                        Job.status == "running",
                        Job.job_type != "export",
                        Job.created_at < default_cutoff,
                    )
                )
                stuck_jobs = list(result.scalars().all())

                # Find stuck export jobs (longer timeout)
                export_cutoff = now - export_timeout
                result = await db.execute(
                    select(Job).where(
                        Job.status == "running",
                        Job.job_type == "export",
                        Job.created_at < export_cutoff,
                    )
                )
                stuck_exports = list(result.scalars().all())

                all_stuck = stuck_jobs + stuck_exports

                for job in all_stuck:
                    job.status = "failed"
                    job.error = "Job timed out (stuck detection)"
                    job.completed_at = now
                    logger.warning(
                        "Marked stuck job %s (%s) as failed — created at %s",
                        job.id,
                        job.job_type,
                        job.created_at,
                    )

                if all_stuck:
                    await db.commit()
                    logger.info("Reset %d stuck jobs", len(all_stuck))

        except Exception as e:
            logger.error("Error in stuck job detection: %s", e, exc_info=True)

        await asyncio.sleep(120)


async def resume_stuck_style_transfers():
    """Re-submit photos stuck in 'styling' status from a previous server shutdown."""
    try:
        async with background_session_maker() as db:
            result = await db.execute(
                select(Photo, Project)
                .join(Project, Photo.project_id == Project.id)
                .where(Photo.status == "styling")
            )
            rows = result.all()

            if not rows:
                return

            logger.info("Found %d photos stuck in 'styling' — resuming style transfers", len(rows))

            from app.api.routes.styles import process_style_transfer_for_photo

            for photo, project in rows:
                style = project.style
                if not style:
                    logger.warning(
                        "Photo %s stuck in styling but project %s has no style set — resetting",
                        photo.id,
                        project.id,
                    )
                    photo.status = "uploaded"
                    continue

                logger.info(
                    "Resuming style transfer for photo %s (style=%s)", photo.id, style
                )
                asyncio.create_task(
                    process_style_transfer_for_photo(
                        photo.id,
                        style,
                        save_as_variant=True,
                        custom_prompt=project.style_prompt,
                    )
                )

            await db.commit()

    except Exception as e:
        logger.error("Failed to resume stuck style transfers: %s", e, exc_info=True)
