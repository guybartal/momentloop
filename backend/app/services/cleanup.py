"""File cleanup service for removing old exports and orphaned files."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import background_session_maker
from app.models.photo import Photo
from app.models.video import Export, Video

logger = logging.getLogger(__name__)
settings = get_settings()


class CleanupService:
    """Service for cleaning up old and orphaned files."""

    def __init__(self):
        self.storage_path = settings.storage_path

    async def cleanup_old_exports(self, retention_days: int | None = None) -> int:
        """
        Delete exports older than the retention period.

        Args:
            retention_days: Number of days to keep exports (defaults to config)

        Returns:
            Number of deleted exports
        """
        if retention_days is None:
            retention_days = settings.export_retention_days

        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
        deleted_count = 0

        async with background_session_maker() as db:
            result = await db.execute(
                select(Export).where(
                    Export.created_at < cutoff_date,
                    Export.status == "ready",
                )
            )
            old_exports = result.scalars().all()

            for export in old_exports:
                try:
                    if export.file_path:
                        file_path = self.storage_path / export.file_path
                        if file_path.exists():
                            file_path.unlink()
                            logger.info("Deleted old export file: %s", file_path)

                    await db.delete(export)
                    deleted_count += 1
                except Exception as e:
                    logger.error("Failed to delete export %s: %s", export.id, e)

            await db.commit()

        logger.info("Cleaned up %d old exports", deleted_count)
        return deleted_count

    async def cleanup_orphaned_files(self) -> dict[str, int]:
        """
        Find and delete files in storage that are not referenced in the database.

        Returns:
            Dictionary with counts of deleted files by type
        """
        if not settings.orphan_cleanup_enabled:
            logger.info("Orphan cleanup is disabled")
            return {"uploads": 0, "styled": 0, "videos": 0}

        deleted = {"uploads": 0, "styled": 0, "videos": 0}

        async with background_session_maker() as db:
            # Get all referenced paths from database
            photo_result = await db.execute(select(Photo.original_path, Photo.styled_path))
            photo_paths = set()
            for row in photo_result:
                if row[0]:
                    photo_paths.add(row[0])
                if row[1]:
                    photo_paths.add(row[1])

            video_result = await db.execute(select(Video.video_path))
            video_paths = {row[0] for row in video_result if row[0]}

            export_result = await db.execute(select(Export.file_path))
            export_paths = {row[0] for row in export_result if row[0]}

            all_referenced = photo_paths | video_paths | export_paths

        # Check uploads directory
        uploads_dir = settings.uploads_path
        if uploads_dir.exists():
            deleted["uploads"] = self._cleanup_directory(uploads_dir, all_referenced, "uploads")

        # Check styled directory
        styled_dir = settings.styled_path
        if styled_dir.exists():
            deleted["styled"] = self._cleanup_directory(styled_dir, all_referenced, "styled")

        # Check videos directory
        videos_dir = settings.videos_path
        if videos_dir.exists():
            deleted["videos"] = self._cleanup_directory(videos_dir, all_referenced, "videos")

        logger.info(
            "Cleaned up orphaned files: %d uploads, %d styled, %d videos",
            deleted["uploads"],
            deleted["styled"],
            deleted["videos"],
        )
        return deleted

    def _cleanup_directory(
        self,
        directory: Path,
        referenced_paths: set[str],
        category: str,
    ) -> int:
        """Clean up orphaned files in a directory."""
        deleted_count = 0

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue

            # Get relative path from storage root
            try:
                relative_path = str(file_path.relative_to(self.storage_path))
            except ValueError:
                continue

            if relative_path not in referenced_paths:
                try:
                    file_path.unlink()
                    logger.debug("Deleted orphaned %s file: %s", category, file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.error("Failed to delete orphaned file %s: %s", file_path, e)

        return deleted_count

    async def cleanup_failed_exports(self) -> int:
        """Delete export records that failed processing."""
        deleted_count = 0

        async with background_session_maker() as db:
            result = await db.execute(select(Export).where(Export.status == "failed"))
            failed_exports = result.scalars().all()

            for export in failed_exports:
                await db.delete(export)
                deleted_count += 1

            await db.commit()

        logger.info("Cleaned up %d failed exports", deleted_count)
        return deleted_count

    async def run_full_cleanup(self) -> dict:
        """Run all cleanup tasks."""
        results = {
            "old_exports": await self.cleanup_old_exports(),
            "failed_exports": await self.cleanup_failed_exports(),
            "orphaned_files": await self.cleanup_orphaned_files(),
        }
        logger.info("Full cleanup completed: %s", results)
        return results


# Global service instance
cleanup_service = CleanupService()
