import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from app.core.config import get_settings

settings = get_settings()


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save_upload(self, file_content: bytes, filename: str, project_id: uuid.UUID) -> str:
        ...

    @abstractmethod
    async def save_styled(self, file_content: bytes, original_path: str) -> str:
        ...

    @abstractmethod
    async def save_video(
        self, file_content: bytes, project_id: uuid.UUID, video_type: str = "scene"
    ) -> str:
        ...

    @abstractmethod
    async def save_export(self, file_content: bytes, project_id: uuid.UUID) -> str:
        ...

    @abstractmethod
    async def save_thumbnail(
        self, file_content: bytes, project_id: uuid.UUID, export_id: uuid.UUID
    ) -> str:
        ...

    @abstractmethod
    def get_full_path(self, relative_path: str) -> Path:
        ...

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        ...

    @abstractmethod
    async def delete_file(self, relative_path: str) -> bool:
        ...

    @abstractmethod
    async def delete_project_files(self, project_id: uuid.UUID) -> None:
        ...

    @abstractmethod
    async def read_file(self, relative_path: str) -> bytes:
        ...


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or settings.storage_path
        self.uploads_path = self.base_path / "uploads"
        self.styled_path = self.base_path / "styled"
        self.videos_path = self.base_path / "videos"
        self.exports_path = self.base_path / "exports"
        self.thumbnails_path = self.base_path / "thumbnails"

    async def save_upload(self, file_content: bytes, filename: str, project_id: uuid.UUID) -> str:
        project_dir = self.uploads_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_styled(self, file_content: bytes, original_path: str) -> str:
        parts = Path(original_path).parts
        project_id = parts[1] if len(parts) >= 2 else "unknown"

        project_dir = self.styled_path / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        original_filename = Path(original_path).stem
        unique_filename = f"{original_filename}_styled_{uuid.uuid4()}.png"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_video(
        self, file_content: bytes, project_id: uuid.UUID, video_type: str = "scene"
    ) -> str:
        project_dir = self.videos_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"{video_type}_{uuid.uuid4()}.mp4"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    async def save_export(self, file_content: bytes, project_id: uuid.UUID) -> str:
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
        project_dir = self.thumbnails_path / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"thumb_{export_id}.jpg"
        file_path = project_dir / unique_filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        return str(file_path.relative_to(self.base_path))

    def get_full_path(self, relative_path: str) -> Path:
        full_path = (self.base_path / relative_path).resolve()
        base_resolved = self.base_path.resolve()
        if not str(full_path).startswith(str(base_resolved) + "/") and full_path != base_resolved:
            raise ValueError("Invalid path: path traversal detected")
        return full_path

    def get_url(self, relative_path: str) -> str:
        return f"/storage/{relative_path}"

    async def delete_file(self, relative_path: str) -> bool:
        file_path = self.get_full_path(relative_path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def delete_project_files(self, project_id: uuid.UUID) -> None:
        for path in [
            self.uploads_path,
            self.styled_path,
            self.videos_path,
            self.exports_path,
            self.thumbnails_path,
        ]:
            project_dir = path / str(project_id)
            if project_dir.exists():
                shutil.rmtree(project_dir)

    async def read_file(self, relative_path: str) -> bytes:
        file_path = self.get_full_path(relative_path)
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()


def create_storage_service() -> StorageBackend:
    """Factory: create the right storage backend based on config."""
    if settings.storage_backend == "azure":
        from app.services.azure_storage import AzureBlobStorageBackend
        return AzureBlobStorageBackend()
    return LocalStorageBackend()


storage_service = create_storage_service()
