"""Azure Blob Storage backend for file storage."""

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

import aiofiles
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from app.core.config import get_settings
from app.services.storage import StorageBackend

logger = logging.getLogger(__name__)
settings = get_settings()

# Map relative path prefixes to blob container names
CONTAINER_MAP = {
    "uploads": "uploads",
    "styled": "styled",
    "videos": "videos",
    "exports": "exports",
    "thumbnails": "thumbnails",
}


def _parse_path(relative_path: str) -> tuple[str, str]:
    """Parse a relative path into (container_name, blob_name).

    Example: 'uploads/project-id/file.jpg' -> ('uploads', 'project-id/file.jpg')
    """
    parts = relative_path.split("/", 1)
    container = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    if container not in CONTAINER_MAP:
        raise ValueError(f"Unknown storage container: {container}")
    return CONTAINER_MAP[container], blob_name


class AzureBlobStorageBackend(StorageBackend):
    """Azure Blob Storage backend using Managed Identity."""

    def __init__(self):
        account_name = settings.azure_storage_account_name
        if not account_name:
            raise ValueError("AZURE_STORAGE_ACCOUNT_NAME is required when STORAGE_BACKEND=azure")

        account_url = f"https://{account_name}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        self._client = BlobServiceClient(account_url, credential=credential)
        self._temp_dir = Path(tempfile.mkdtemp(prefix="momentloop_"))
        logger.info("Azure Blob Storage backend initialized: %s", account_url)

    def _get_container(self, container_name: str):
        return self._client.get_container_client(container_name)

    async def save_upload(self, file_content: bytes, filename: str, project_id: uuid.UUID) -> str:
        ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{ext}"
        blob_name = f"{project_id}/{unique_filename}"
        relative_path = f"uploads/{blob_name}"

        container = self._get_container("uploads")
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(file_content, overwrite=True)

        return relative_path

    async def save_styled(self, file_content: bytes, original_path: str) -> str:
        parts = Path(original_path).parts
        project_id = parts[1] if len(parts) >= 2 else "unknown"
        original_filename = Path(original_path).stem
        unique_filename = f"{original_filename}_styled_{uuid.uuid4()}.png"
        blob_name = f"{project_id}/{unique_filename}"
        relative_path = f"styled/{blob_name}"

        container = self._get_container("styled")
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(file_content, overwrite=True)

        return relative_path

    async def save_video(
        self, file_content: bytes, project_id: uuid.UUID, video_type: str = "scene"
    ) -> str:
        unique_filename = f"{video_type}_{uuid.uuid4()}.mp4"
        blob_name = f"{project_id}/{unique_filename}"
        relative_path = f"videos/{blob_name}"

        container = self._get_container("videos")
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(file_content, overwrite=True)

        return relative_path

    async def save_export(self, file_content: bytes, project_id: uuid.UUID) -> str:
        unique_filename = f"export_{uuid.uuid4()}.mp4"
        blob_name = f"{project_id}/{unique_filename}"
        relative_path = f"exports/{blob_name}"

        container = self._get_container("exports")
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(file_content, overwrite=True)

        return relative_path

    async def save_thumbnail(
        self, file_content: bytes, project_id: uuid.UUID, export_id: uuid.UUID
    ) -> str:
        unique_filename = f"thumb_{export_id}.jpg"
        blob_name = f"{project_id}/{unique_filename}"
        relative_path = f"thumbnails/{blob_name}"

        container = self._get_container("thumbnails")
        blob = container.get_blob_client(blob_name)
        blob.upload_blob(file_content, overwrite=True)

        return relative_path

    def get_full_path(self, relative_path: str) -> Path:
        """Download blob to temp dir and return local path.

        This is needed for FFmpeg and image processing that require
        local filesystem paths.
        """
        container_name, blob_name = _parse_path(relative_path)
        local_path = self._temp_dir / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)

        container = self._get_container(container_name)
        blob = container.get_blob_client(blob_name)
        with open(local_path, "wb") as f:
            download_stream = blob.download_blob()
            f.write(download_stream.readall())

        return local_path

    def get_url(self, relative_path: str) -> str:
        """Return proxy URL — backend streams from blob storage."""
        return f"/api/storage/{relative_path}"

    async def delete_file(self, relative_path: str) -> bool:
        try:
            container_name, blob_name = _parse_path(relative_path)
            container = self._get_container(container_name)
            blob = container.get_blob_client(blob_name)
            blob.delete_blob()
            return True
        except Exception:
            logger.warning("Failed to delete blob: %s", relative_path, exc_info=True)
            return False

    async def delete_project_files(self, project_id: uuid.UUID) -> None:
        for container_name in CONTAINER_MAP.values():
            container = self._get_container(container_name)
            prefix = f"{project_id}/"
            try:
                blobs = container.list_blobs(name_starts_with=prefix)
                for blob in blobs:
                    container.delete_blob(blob.name)
            except Exception:
                logger.warning(
                    "Failed to delete blobs in %s/%s", container_name, prefix, exc_info=True
                )

        # Clean up temp files too
        temp_project = self._temp_dir / str(project_id)
        if temp_project.exists():
            shutil.rmtree(temp_project)

    async def read_file(self, relative_path: str) -> bytes:
        container_name, blob_name = _parse_path(relative_path)
        container = self._get_container(container_name)
        blob = container.get_blob_client(blob_name)
        download_stream = blob.download_blob()
        return download_stream.readall()
