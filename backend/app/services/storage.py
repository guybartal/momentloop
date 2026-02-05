import shutil
import uuid
from pathlib import Path

import aiofiles

from app.core.config import get_settings

settings = get_settings()


class StorageService:
    """File storage service with abstraction for future cloud migration."""

    def __init__(self):
        self.base_path = settings.storage_path
        self.uploads_path = settings.uploads_path
        self.styled_path = settings.styled_path
        self.videos_path = settings.videos_path
        self.exports_path = settings.exports_path
        self.thumbnails_path = settings.storage_path / "thumbnails"

    async def save_upload(self, file_content: bytes, filename: str, project_id: uuid.UUID) -> str:
        """Save an uploaded file and return the relative path."""
        # Create project directory
        project_dir = self.uploads_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = project_dir / unique_filename

        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        # Return relative path from storage root
        return str(file_path.relative_to(self.base_path))

    async def save_styled(self, file_content: bytes, original_path: str) -> str:
        """Save a styled image and return the relative path."""
        # Parse original path to get project ID
        parts = Path(original_path).parts
        if len(parts) >= 2:
            project_id = parts[1]  # uploads/project_id/filename
        else:
            project_id = "unknown"

        # Create project directory in styled
        project_dir = self.styled_path / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        original_filename = Path(original_path).stem
        unique_filename = f"{original_filename}_styled_{uuid.uuid4()}.png"
        file_path = project_dir / unique_filename

        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_video(self, file_content: bytes, project_id: uuid.UUID, video_type: str = "scene") -> str:
        """Save a generated video and return the relative path."""
        project_dir = self.videos_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"{video_type}_{uuid.uuid4()}.mp4"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_export(self, file_content: bytes, project_id: uuid.UUID) -> str:
        """Save an exported video and return the relative path."""
        project_dir = self.exports_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"export_{uuid.uuid4()}.mp4"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_thumbnail(
        self, file_content: bytes, project_id: uuid.UUID, export_id: uuid.UUID
    ) -> str:
        """Save an export thumbnail and return the relative path."""
        project_dir = self.thumbnails_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"thumb_{export_id}.jpg"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    def get_full_path(self, relative_path: str) -> Path:
        """Get the full filesystem path from a relative path."""
        full_path = (self.base_path / relative_path).resolve()
        base_resolved = self.base_path.resolve()
        # Ensure the resolved path is within the base storage directory
        if not str(full_path).startswith(str(base_resolved) + "/") and full_path != base_resolved:
            raise ValueError("Invalid path: path traversal detected")
        return full_path

    def get_url(self, relative_path: str) -> str:
        """Get the URL for serving a file."""
        return f"/storage/{relative_path}"

    async def delete_file(self, relative_path: str) -> bool:
        """Delete a file and return True if successful."""
        file_path = self.get_full_path(relative_path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def delete_project_files(self, project_id: uuid.UUID) -> None:
        """Delete all files for a project."""
        for path in [self.uploads_path, self.styled_path, self.videos_path, self.exports_path, self.thumbnails_path]:
            project_dir = path / str(project_id)
            if project_dir.exists():
                shutil.rmtree(project_dir)


storage_service = StorageService()
