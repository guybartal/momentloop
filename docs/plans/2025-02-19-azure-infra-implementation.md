# Azure Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy MomentLoop to Azure using Bicep IaC with azd, supporting dual-mode (local + Azure) operation and parameterized SKUs for cost control.

**Architecture:** Modular Bicep under `infra/` with azd manifest. Two Container Apps (frontend nginx + backend FastAPI), PostgreSQL Flexible Server, Blob Storage, Key Vault, ACR, Log Analytics. All Azure connections use System-Assigned Managed Identity.

**Tech Stack:** Bicep, azd, GitHub Actions, azure-storage-blob SDK, azure-identity SDK

**Design Doc:** `docs/plans/2025-02-19-azure-infra-design.md`

---

## Task 1: Add Azure dependencies to backend

**Files:**
- Modify: `backend/pyproject.toml:6-27`

**Step 1: Add azure optional dependency group**

Add an `azure` optional dependency group to `pyproject.toml` after the `dev` group (line 36):

```toml
azure = [
    "azure-storage-blob>=12.19.0",
    "azure-identity>=1.15.0",
]
```

This keeps Azure SDK optional — local dev doesn't need it.

**Step 2: Install and verify**

Run: `cd backend && uv sync --extra azure --extra dev`
Expected: Installs azure-storage-blob and azure-identity without errors.

**Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "build: add azure-storage-blob and azure-identity as optional deps"
```

---

## Task 2: Add Azure storage settings to config

**Files:**
- Modify: `backend/app/core/config.py`

**Step 1: Write the failing test**

Create `backend/tests/test_config.py`:

```python
"""Tests for configuration settings."""

import os

import pytest


def test_storage_backend_defaults_to_local():
    """STORAGE_BACKEND should default to 'local'."""
    from app.core.config import Settings
    s = Settings(jwt_secret="a" * 32)
    assert s.storage_backend == "local"


def test_storage_backend_accepts_azure():
    """STORAGE_BACKEND should accept 'azure'."""
    from app.core.config import Settings
    s = Settings(jwt_secret="a" * 32, storage_backend="azure")
    assert s.storage_backend == "azure"


def test_storage_backend_rejects_invalid():
    """STORAGE_BACKEND should reject invalid values."""
    from app.core.config import Settings
    with pytest.raises(ValueError):
        Settings(jwt_secret="a" * 32, storage_backend="s3")


def test_azure_storage_account_name_setting():
    """Azure storage account name should be configurable."""
    from app.core.config import Settings
    s = Settings(jwt_secret="a" * 32, azure_storage_account_name="myaccount")
    assert s.azure_storage_account_name == "myaccount"


def test_thumbnails_path_property():
    """thumbnails_path should be derived from storage_path."""
    from app.core.config import Settings
    s = Settings(jwt_secret="a" * 32)
    assert str(s.thumbnails_path).endswith("thumbnails")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: FAIL — `storage_backend` attribute not found.

**Step 3: Add settings to config.py**

Add the following fields to the `Settings` class in `backend/app/core/config.py` after the `storage_path` line (line 65):

```python
    # Storage backend: "local" (default) or "azure"
    storage_backend: str = "local"

    # Azure Blob Storage (only used when storage_backend="azure")
    azure_storage_account_name: str = ""

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, v: str) -> str:
        if v not in ("local", "azure"):
            raise ValueError(f"storage_backend must be 'local' or 'azure', got '{v}'")
        return v
```

Also add a `thumbnails_path` property (currently missing from config but used by StorageService):

```python
    @property
    def thumbnails_path(self) -> Path:
        return self.storage_path / "thumbnails"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat: add storage_backend and Azure config settings"
```

---

## Task 3: Refactor StorageService into dual-mode backend

**Files:**
- Modify: `backend/app/services/storage.py`
- Create: `backend/tests/test_storage.py`

This is the core change. The existing `StorageService` becomes `LocalStorageBackend`. A new `AzureBlobStorageBackend` implements the same interface. A factory function picks the right backend based on config.

**Step 1: Write tests for the storage abstraction**

Create `backend/tests/test_storage.py`:

```python
"""Tests for storage service dual-mode backend."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary storage directory structure."""
    for subdir in ["uploads", "styled", "videos", "exports", "thumbnails"]:
        (tmp_path / subdir).mkdir()
    return tmp_path


class TestLocalStorageBackend:
    """Tests for the local file storage backend."""

    async def test_save_upload(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        path = await backend.save_upload(b"fake image data", "photo.jpg", project_id)

        assert path.startswith("uploads/")
        assert str(project_id) in path
        assert path.endswith(".jpg")

        # Verify file exists on disk
        full_path = temp_storage / path
        assert full_path.exists()
        assert full_path.read_bytes() == b"fake image data"

    async def test_save_styled(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        path = await backend.save_styled(b"styled data", "uploads/proj123/photo.jpg")

        assert path.startswith("styled/")
        assert "proj123" in path
        assert "_styled_" in path

    async def test_save_video(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        path = await backend.save_video(b"video data", project_id, "scene")

        assert path.startswith("videos/")
        assert "scene_" in path
        assert path.endswith(".mp4")

    async def test_save_export(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        path = await backend.save_export(b"export data", project_id)

        assert path.startswith("exports/")
        assert "export_" in path

    async def test_save_thumbnail(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        export_id = uuid.uuid4()
        path = await backend.save_thumbnail(b"thumb data", project_id, export_id)

        assert path.startswith("thumbnails/")
        assert f"thumb_{export_id}" in path

    async def test_get_full_path(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        rel_path = await backend.save_upload(b"data", "test.jpg", project_id)
        full_path = backend.get_full_path(rel_path)

        assert full_path.exists()
        assert full_path.is_absolute()

    async def test_get_full_path_rejects_traversal(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        with pytest.raises(ValueError, match="path traversal"):
            backend.get_full_path("../../etc/passwd")

    async def test_get_url_local(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        url = backend.get_url("uploads/proj/photo.jpg")
        assert url == "/storage/uploads/proj/photo.jpg"

    async def test_delete_file(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        rel_path = await backend.save_upload(b"data", "test.jpg", project_id)

        assert await backend.delete_file(rel_path) is True
        assert not (temp_storage / rel_path).exists()

    async def test_delete_file_nonexistent(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        assert await backend.delete_file("nonexistent/file.jpg") is False

    async def test_delete_project_files(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        await backend.save_upload(b"data", "test.jpg", project_id)
        await backend.save_video(b"video", project_id, "scene")

        await backend.delete_project_files(project_id)

        assert not (temp_storage / "uploads" / str(project_id)).exists()
        assert not (temp_storage / "videos" / str(project_id)).exists()

    async def test_read_file(self, temp_storage):
        from app.services.storage import LocalStorageBackend
        backend = LocalStorageBackend(temp_storage)

        project_id = uuid.uuid4()
        rel_path = await backend.save_upload(b"hello world", "test.txt", project_id)

        data = await backend.read_file(rel_path)
        assert data == b"hello world"


class TestStorageServiceFactory:
    """Test that the correct backend is created based on config."""

    def test_local_backend_created_by_default(self):
        from app.services.storage import storage_service
        from app.services.storage import LocalStorageBackend
        # Default config should create local backend
        assert isinstance(storage_service, LocalStorageBackend)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_storage.py -v`
Expected: FAIL — `LocalStorageBackend` not found.

**Step 3: Refactor storage.py**

Rewrite `backend/app/services/storage.py`. The key changes:
- Rename `StorageService` to `LocalStorageBackend`
- Accept `base_path` as constructor parameter (instead of reading from global settings)
- Add `read_file()` method (needed for Azure proxy to read local files too)
- Add a factory function `create_storage_service()` that picks the backend
- Keep `storage_service` as the module-level singleton

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storage.py -v`
Expected: All PASS.

**Step 5: Run existing tests to verify no regressions**

Run: `cd backend && uv run pytest -v`
Expected: All existing tests still pass (the module-level `storage_service` is still a `LocalStorageBackend` by default).

**Step 6: Commit**

```bash
git add backend/app/services/storage.py backend/tests/test_storage.py
git commit -m "refactor: extract LocalStorageBackend with abstract base class for dual-mode storage"
```

---

## Task 4: Implement AzureBlobStorageBackend

**Files:**
- Create: `backend/app/services/azure_storage.py`
- Create: `backend/tests/test_azure_storage.py`

**Step 1: Write tests (mocked Azure SDK)**

Create `backend/tests/test_azure_storage.py`:

```python
"""Tests for Azure Blob Storage backend (mocked SDK calls)."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_blob_service():
    """Mock Azure BlobServiceClient."""
    with patch("app.services.azure_storage.BlobServiceClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Mock container clients
        mock_container = MagicMock()
        mock_client.get_container_client.return_value = mock_container

        # Mock blob client
        mock_blob = MagicMock()
        mock_container.get_blob_client.return_value = mock_blob
        mock_blob.upload_blob = MagicMock()

        yield mock_client


@pytest.fixture
def mock_default_credential():
    """Mock DefaultAzureCredential."""
    with patch("app.services.azure_storage.DefaultAzureCredential") as mock_cls:
        mock_cls.return_value = MagicMock()
        yield mock_cls


class TestAzureBlobStorageBackend:
    """Tests for AzureBlobStorageBackend with mocked Azure SDK."""

    def _create_backend(self, mock_blob_service, mock_default_credential):
        with patch("app.services.azure_storage.get_settings") as mock_settings:
            mock_settings.return_value.storage_backend = "azure"
            mock_settings.return_value.azure_storage_account_name = "testaccount"
            mock_settings.return_value.storage_path = Path("/tmp/momentloop-test")
            from app.services.azure_storage import AzureBlobStorageBackend
            return AzureBlobStorageBackend()

    async def test_save_upload_uploads_to_blob(self, mock_blob_service, mock_default_credential):
        backend = self._create_backend(mock_blob_service, mock_default_credential)
        project_id = uuid.uuid4()

        path = await backend.save_upload(b"image data", "photo.jpg", project_id)

        assert path.startswith("uploads/")
        assert str(project_id) in path
        # Verify blob upload was called
        mock_blob_service.get_container_client.assert_called()

    async def test_get_url_returns_proxy_path(self, mock_blob_service, mock_default_credential):
        backend = self._create_backend(mock_blob_service, mock_default_credential)

        url = backend.get_url("uploads/proj/photo.jpg")
        assert url == "/api/storage/uploads/proj/photo.jpg"

    async def test_delete_file_deletes_blob(self, mock_blob_service, mock_default_credential):
        backend = self._create_backend(mock_blob_service, mock_default_credential)

        mock_blob = mock_blob_service.get_container_client.return_value.get_blob_client.return_value
        mock_blob.delete_blob = MagicMock()

        result = await backend.delete_file("uploads/proj/photo.jpg")
        assert result is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_azure_storage.py -v`
Expected: FAIL — module `azure_storage` not found.

**Step 3: Implement AzureBlobStorageBackend**

Create `backend/app/services/azure_storage.py`:

```python
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


class AzureBlobStorageBackend:
    """Azure Blob Storage backend using Managed Identity."""

    def __init__(self):
        from app.services.storage import StorageBackend

        self.__class__.__bases__ = (StorageBackend,)
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_azure_storage.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add backend/app/services/azure_storage.py backend/tests/test_azure_storage.py
git commit -m "feat: add AzureBlobStorageBackend for Azure mode"
```

---

## Task 5: Add storage proxy route for Azure mode

**Files:**
- Create: `backend/app/api/routes/storage_proxy.py`
- Modify: `backend/app/main.py`

**Step 1: Create the proxy route**

Create `backend/app/api/routes/storage_proxy.py`:

```python
"""Storage proxy route for serving files from any storage backend."""

import logging
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/storage/{file_path:path}")
async def serve_storage_file(file_path: str):
    """Serve a file from the storage backend.

    In local mode, this is unused (FastAPI StaticFiles handles /storage/).
    In Azure mode, this streams files from Blob Storage.
    """
    try:
        data = await storage_service.read_file(file_path)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail="File not found") from e
    except Exception as e:
        logger.error("Error reading file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Error reading file") from e

    # Guess content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    return Response(content=data, media_type=content_type)
```

**Step 2: Modify main.py for conditional static files vs proxy**

In `backend/app/main.py`, replace the static files mount (line 94-95) with conditional logic:

```python
# Conditional file serving based on storage backend
if settings.storage_backend == "azure":
    # Azure mode: use proxy route to stream from Blob Storage
    from app.api.routes import storage_proxy
    app.include_router(storage_proxy.router, prefix="/api", tags=["Storage"])
else:
    # Local mode: serve files directly from disk (current behavior)
    app.mount("/storage", StaticFiles(directory=str(settings.storage_path)), name="storage")
```

**Step 3: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: All PASS. Local mode behavior unchanged.

**Step 4: Commit**

```bash
git add backend/app/api/routes/storage_proxy.py backend/app/main.py
git commit -m "feat: add storage proxy route for Azure mode, conditional static files"
```

---

## Task 6: Create Bicep modules — monitoring and container registry

**Files:**
- Create: `infra/modules/monitoring.bicep`
- Create: `infra/modules/container-registry.bicep`

**Step 1: Create monitoring module**

Create `infra/modules/monitoring.bicep`:

```bicep
// Log Analytics Workspace for Container Apps monitoring
param name string
param location string
param tags object = {}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

output id string = logAnalytics.id
output customerId string = logAnalytics.properties.customerId
output sharedKey string = listKeys(logAnalytics.id, '2023-09-01').primarySharedKey
```

**Step 2: Create container registry module**

Create `infra/modules/container-registry.bicep`:

```bicep
// Azure Container Registry for storing Docker images
param name string
param location string
param tags object = {}
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

output id string = acr.id
output name string = acr.name
output loginServer string = acr.properties.loginServer
```

**Step 3: Commit**

```bash
git add infra/modules/monitoring.bicep infra/modules/container-registry.bicep
git commit -m "infra: add Log Analytics and Container Registry Bicep modules"
```

---

## Task 7: Create Bicep modules — storage and key vault

**Files:**
- Create: `infra/modules/storage.bicep`
- Create: `infra/modules/key-vault.bicep`

**Step 1: Create storage module**

Create `infra/modules/storage.bicep`:

```bicep
// Azure Storage Account with blob containers for media files
param name string
param location string
param tags object = {}
param skuName string = 'Standard_LRS'

// Managed Identity principal ID for RBAC
param backendPrincipalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false  // Managed Identity only
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

// Create blob containers for each media type
var containerNames = ['uploads', 'styled', 'videos', 'exports', 'thumbnails']

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in containerNames: {
    parent: blobService
    name: containerName
    properties: {
      publicAccess: 'None'
    }
  }
]

// RBAC: Storage Blob Data Contributor for backend managed identity
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, backendPrincipalId, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
    )
    principalId: backendPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output id string = storageAccount.id
output name string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
```

**Step 2: Create key vault module**

Create `infra/modules/key-vault.bicep`:

```bicep
// Azure Key Vault for storing external API secrets
param name string
param location string
param tags object = {}

// Managed Identity principal ID for RBAC
param backendPrincipalId string

// Secrets to store (passed as secure parameters)
@secure()
param googleClientId string = ''
@secure()
param googleClientSecret string = ''
@secure()
param googleAiApiKey string = ''
@secure()
param falKey string = ''
@secure()
param jwtSecret string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
    // Do NOT disable purge protection per Azure best practices
  }
}

// RBAC: Key Vault Secrets User for backend managed identity
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendPrincipalId, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
    )
    principalId: backendPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Store secrets (only if non-empty values provided)
resource secretGoogleClientId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleClientId)) {
  parent: keyVault
  name: 'google-client-id'
  properties: {
    value: googleClientId
  }
}

resource secretGoogleClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleClientSecret)) {
  parent: keyVault
  name: 'google-client-secret'
  properties: {
    value: googleClientSecret
  }
}

resource secretGoogleAiApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleAiApiKey)) {
  parent: keyVault
  name: 'google-ai-api-key'
  properties: {
    value: googleAiApiKey
  }
}

resource secretFalKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(falKey)) {
  parent: keyVault
  name: 'fal-key'
  properties: {
    value: falKey
  }
}

resource secretJwtSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(jwtSecret)) {
  parent: keyVault
  name: 'jwt-secret'
  properties: {
    value: jwtSecret
  }
}

output id string = keyVault.id
output name string = keyVault.name
output uri string = keyVault.properties.vaultUri
```

**Step 3: Commit**

```bash
git add infra/modules/storage.bicep infra/modules/key-vault.bicep
git commit -m "infra: add Storage Account and Key Vault Bicep modules"
```

---

## Task 8: Create Bicep modules — PostgreSQL

**Files:**
- Create: `infra/modules/postgresql.bicep`

**Step 1: Create PostgreSQL module**

Create `infra/modules/postgresql.bicep`:

```bicep
// Azure Database for PostgreSQL Flexible Server with Entra auth
param name string
param location string
param tags object = {}

// SKU parameters (configurable for cost control)
param skuName string = 'Standard_B1ms'
param skuTier string = 'Burstable'
param storageSizeGB int = 32
param haMode string = 'Disabled'
param version string = '16'
param databaseName string = 'momentloop'

// Managed Identity for Entra authentication
param backendPrincipalId string

// Admin - used for initial setup only
param administratorLogin string = 'momentloopadmin'
@secure()
param administratorPassword string

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    storage: {
      storageSizeGB: storageSizeGB
    }
    highAvailability: {
      mode: haMode
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled' // Keep password auth for initial setup
    }
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
  }
}

// Create the application database
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Allow Azure services to connect (for Container Apps)
resource firewallAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output id string = postgres.id
output name string = postgres.name
output fqdn string = postgres.properties.fullyQualifiedDomainName
output databaseName string = databaseName
```

**Step 2: Commit**

```bash
git add infra/modules/postgresql.bicep
git commit -m "infra: add PostgreSQL Flexible Server Bicep module"
```

---

## Task 9: Create Bicep modules — Container Apps

**Files:**
- Create: `infra/modules/container-apps-env.bicep`
- Create: `infra/modules/container-app-backend.bicep`
- Create: `infra/modules/container-app-frontend.bicep`

**Step 1: Create Container Apps Environment module**

Create `infra/modules/container-apps-env.bicep`:

```bicep
// Container Apps managed environment with Log Analytics
param name string
param location string
param tags object = {}
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string

resource env 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

output id string = env.id
output name string = env.name
output defaultDomain string = env.properties.defaultDomain
```

**Step 2: Create backend Container App module**

Create `infra/modules/container-app-backend.bicep`:

```bicep
// Backend Container App (FastAPI + uvicorn)
param name string
param location string
param tags object = {}
param environmentId string

// Container configuration (configurable SKUs)
param containerImage string
param cpu string = '0.25'
param memory string = '0.5Gi'
param minReplicas int = 0
param maxReplicas int = 3

// ACR configuration
param acrLoginServer string

// Environment variables
param databaseUrl string
param storageAccountName string
param keyVaultName string
param corsOrigins string = ''

// Key Vault secret URIs
param keyVaultUri string

resource backend 'Microsoft.App/containerApps@2025-01-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: empty(corsOrigins) ? ['*'] : split(corsOrigins, ',')
          allowedMethods: ['*']
          allowedHeaders: ['*']
          allowCredentials: true
        }
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'google-client-id'
          keyVaultUrl: '${keyVaultUri}secrets/google-client-id'
          identity: 'system'
        }
        {
          name: 'google-client-secret'
          keyVaultUrl: '${keyVaultUri}secrets/google-client-secret'
          identity: 'system'
        }
        {
          name: 'google-ai-api-key'
          keyVaultUrl: '${keyVaultUri}secrets/google-ai-api-key'
          identity: 'system'
        }
        {
          name: 'fal-key'
          keyVaultUrl: '${keyVaultUri}secrets/fal-key'
          identity: 'system'
        }
        {
          name: 'jwt-secret'
          keyVaultUrl: '${keyVaultUri}secrets/jwt-secret'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'STORAGE_BACKEND', value: 'azure' }
            { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'DATABASE_URL', value: databaseUrl }
            { name: 'GOOGLE_CLIENT_ID', secretRef: 'google-client-id' }
            { name: 'GOOGLE_CLIENT_SECRET', secretRef: 'google-client-secret' }
            { name: 'GOOGLE_AI_API_KEY', secretRef: 'google-ai-api-key' }
            { name: 'FAL_KEY', secretRef: 'fal-key' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'CORS_ORIGINS', value: corsOrigins }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = backend.id
output name string = backend.name
output fqdn string = backend.properties.configuration.ingress.fqdn
output principalId string = backend.identity.principalId
```

**Step 3: Create frontend Container App module**

Create `infra/modules/container-app-frontend.bicep`:

```bicep
// Frontend Container App (React served by nginx)
param name string
param location string
param tags object = {}
param environmentId string

// Container configuration (configurable SKUs)
param containerImage string
param cpu string = '0.25'
param memory string = '0.5Gi'
param minReplicas int = 0
param maxReplicas int = 2

// ACR configuration
param acrLoginServer string

// Backend URL for API proxy
param backendFqdn string

resource frontend 'Microsoft.App/containerApps@2025-01-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'VITE_API_URL', value: 'https://${backendFqdn}' }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = frontend.id
output name string = frontend.name
output fqdn string = frontend.properties.configuration.ingress.fqdn
output principalId string = frontend.identity.principalId
```

**Step 4: Commit**

```bash
git add infra/modules/container-apps-env.bicep infra/modules/container-app-backend.bicep infra/modules/container-app-frontend.bicep
git commit -m "infra: add Container Apps Environment, Backend, and Frontend Bicep modules"
```

---

## Task 10: Create main.bicep orchestrator and parameters

**Files:**
- Create: `infra/main.bicep`
- Create: `infra/main.bicepparam`
- Create: `infra/abbreviations.json`

**Step 1: Create abbreviations.json**

Create `infra/abbreviations.json`:

```json
{
  "Microsoft.App/containerApps": "ca-",
  "Microsoft.App/managedEnvironments": "cae-",
  "Microsoft.ContainerRegistry/registries": "cr",
  "Microsoft.DBforPostgreSQL/flexibleServers": "psql-",
  "Microsoft.KeyVault/vaults": "kv-",
  "Microsoft.OperationalInsights/workspaces": "log-",
  "Microsoft.Storage/storageAccounts": "st"
}
```

**Step 2: Create main.bicep**

Create `infra/main.bicep`:

```bicep
// MomentLoop Azure Infrastructure
// Deploy with: azd provision
targetScope = 'resourceGroup'

// ============================================================
// Parameters — all configurable via main.bicepparam
// ============================================================

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Unique environment name used for resource naming')
param environmentName string

@description('Tags applied to all resources')
param tags object = {}

// -- PostgreSQL SKU parameters --
@description('PostgreSQL compute SKU name (e.g. Standard_B1ms, Standard_D2s_v3)')
param postgresSkuName string = 'Standard_B1ms'
@description('PostgreSQL compute tier (Burstable, GeneralPurpose, MemoryOptimized)')
param postgresSkuTier string = 'Burstable'
@description('PostgreSQL storage size in GB')
param postgresStorageSizeGB int = 32
@description('PostgreSQL HA mode (Disabled, ZoneRedundant)')
param postgresHaMode string = 'Disabled'
@secure()
@description('PostgreSQL admin password (for initial setup)')
param postgresAdminPassword string

// -- Container Apps SKU parameters --
@description('Backend CPU cores (e.g. 0.25, 0.5, 1.0, 2.0)')
param backendCpu string = '0.25'
@description('Backend memory (e.g. 0.5Gi, 1.0Gi, 2.0Gi)')
param backendMemory string = '0.5Gi'
@description('Backend minimum replicas (0 = scale to zero)')
param backendMinReplicas int = 0
@description('Backend maximum replicas')
param backendMaxReplicas int = 3
@description('Frontend CPU cores')
param frontendCpu string = '0.25'
@description('Frontend memory')
param frontendMemory string = '0.5Gi'
@description('Frontend minimum replicas')
param frontendMinReplicas int = 0
@description('Frontend maximum replicas')
param frontendMaxReplicas int = 2

// -- Storage SKU --
@description('Storage account SKU (Standard_LRS, Standard_GRS, etc.)')
param storageSkuName string = 'Standard_LRS'

// -- Container Registry SKU --
@description('Container Registry SKU (Basic, Standard, Premium)')
param acrSku string = 'Basic'

// -- Container images (set by CI/CD or azd deploy) --
param backendImage string = ''
param frontendImage string = ''

// -- Key Vault secrets (set during first deployment) --
@secure()
param googleClientId string = ''
@secure()
param googleClientSecret string = ''
@secure()
param googleAiApiKey string = ''
@secure()
param falKey string = ''
@secure()
param jwtSecret string = ''

// -- CORS --
param corsOrigins string = ''

// ============================================================
// Resource naming
// ============================================================

var resourceToken = toLower(uniqueString(resourceGroup().id, environmentName))

var names = {
  logAnalytics: 'log-${environmentName}'
  acr: 'cr${resourceToken}'
  storageAccount: 'st${resourceToken}'
  keyVault: 'kv-${environmentName}'
  postgres: 'psql-${environmentName}'
  containerAppsEnv: 'cae-${environmentName}'
  backendApp: 'ca-${environmentName}-backend'
  frontendApp: 'ca-${environmentName}-frontend'
}

// ============================================================
// Modules
// ============================================================

// 1. Monitoring (Log Analytics)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    name: names.logAnalytics
    location: location
    tags: tags
  }
}

// 2. Container Registry
module acr 'modules/container-registry.bicep' = {
  name: 'acr'
  params: {
    name: names.acr
    location: location
    tags: tags
    sku: acrSku
  }
}

// 3. Container Apps Environment
module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'containerAppsEnv'
  params: {
    name: names.containerAppsEnv
    location: location
    tags: tags
    logAnalyticsCustomerId: monitoring.outputs.customerId
    logAnalyticsSharedKey: monitoring.outputs.sharedKey
  }
}

// 4. Backend Container App (deployed first to get Managed Identity principal)
module backend 'modules/container-app-backend.bicep' = {
  name: 'backend'
  params: {
    name: names.backendApp
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.id
    containerImage: !empty(backendImage) ? backendImage : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    cpu: backendCpu
    memory: backendMemory
    minReplicas: backendMinReplicas
    maxReplicas: backendMaxReplicas
    acrLoginServer: acr.outputs.loginServer
    databaseUrl: 'postgresql+asyncpg://momentloopadmin:${postgresAdminPassword}@${names.postgres}.postgres.database.azure.com:5432/momentloop?ssl=require'
    storageAccountName: names.storageAccount
    keyVaultName: names.keyVault
    keyVaultUri: keyVault.outputs.uri
    corsOrigins: corsOrigins
  }
}

// 5. Frontend Container App
module frontend 'modules/container-app-frontend.bicep' = {
  name: 'frontend'
  params: {
    name: names.frontendApp
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.id
    containerImage: !empty(frontendImage) ? frontendImage : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    cpu: frontendCpu
    memory: frontendMemory
    minReplicas: frontendMinReplicas
    maxReplicas: frontendMaxReplicas
    acrLoginServer: acr.outputs.loginServer
    backendFqdn: backend.outputs.fqdn
  }
}

// 6. PostgreSQL Flexible Server
module postgres 'modules/postgresql.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    tags: tags
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGB: postgresStorageSizeGB
    haMode: postgresHaMode
    administratorPassword: postgresAdminPassword
    backendPrincipalId: backend.outputs.principalId
  }
}

// 7. Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: names.storageAccount
    location: location
    tags: tags
    skuName: storageSkuName
    backendPrincipalId: backend.outputs.principalId
  }
}

// 8. Key Vault
module keyVault 'modules/key-vault.bicep' = {
  name: 'keyVault'
  params: {
    name: names.keyVault
    location: location
    tags: tags
    backendPrincipalId: backend.outputs.principalId
    googleClientId: googleClientId
    googleClientSecret: googleClientSecret
    googleAiApiKey: googleAiApiKey
    falKey: falKey
    jwtSecret: jwtSecret
  }
}

// 9. RBAC: Backend -> ACR (AcrPull)
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.outputs.id, backend.outputs.principalId, 'AcrPull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: backend.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Frontend -> ACR (AcrPull)
resource acrPullRoleFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.outputs.id, frontend.outputs.principalId, 'AcrPull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: frontend.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================
// Outputs
// ============================================================

output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.loginServer
output BACKEND_FQDN string = backend.outputs.fqdn
output FRONTEND_FQDN string = frontend.outputs.fqdn
output BACKEND_URL string = 'https://${backend.outputs.fqdn}'
output FRONTEND_URL string = 'https://${frontend.outputs.fqdn}'
output POSTGRES_FQDN string = postgres.outputs.fqdn
output STORAGE_ACCOUNT_NAME string = storage.outputs.name
output KEY_VAULT_NAME string = keyVault.outputs.name
```

**Step 3: Create main.bicepparam**

Create `infra/main.bicepparam`:

```bicep
using './main.bicep'

// Environment name — change this per deployment
param environmentName = 'momentloop'

// Tags
param tags = {
  project: 'momentloop'
  environment: 'production'
}

// ============================================================
// SKU Configuration — adjust these to control costs
// ============================================================

// PostgreSQL: Burstable B1ms (~$13/mo) — smallest production-ready SKU
param postgresSkuName = 'Standard_B1ms'
param postgresSkuTier = 'Burstable'
param postgresStorageSizeGB = 32
param postgresHaMode = 'Disabled'

// Backend Container App: 0.25 vCPU, 0.5 GiB — scales to zero
param backendCpu = '0.25'
param backendMemory = '0.5Gi'
param backendMinReplicas = 0
param backendMaxReplicas = 3

// Frontend Container App: 0.25 vCPU, 0.5 GiB — scales to zero
param frontendCpu = '0.25'
param frontendMemory = '0.5Gi'
param frontendMinReplicas = 0
param frontendMaxReplicas = 2

// Storage: Standard LRS (locally redundant)
param storageSkuName = 'Standard_LRS'

// Container Registry: Basic (~$5/mo)
param acrSku = 'Basic'

// ============================================================
// Secrets — provide via azd env set or --parameters
// ============================================================
// param postgresAdminPassword = ''
// param googleClientId = ''
// param googleClientSecret = ''
// param googleAiApiKey = ''
// param falKey = ''
// param jwtSecret = ''
```

**Step 4: Commit**

```bash
git add infra/main.bicep infra/main.bicepparam infra/abbreviations.json
git commit -m "infra: add main.bicep orchestrator with parameterized SKUs"
```

---

## Task 11: Create azure.yaml manifest and production Dockerfiles

**Files:**
- Create: `azure.yaml`
- Create: `frontend/Dockerfile.prod`

The frontend needs a production Dockerfile that builds the React app and serves it with nginx (the current Dockerfile runs the dev server).

**Step 1: Create production frontend Dockerfile**

Create `frontend/Dockerfile.prod`:

```dockerfile
# Build stage
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html

# nginx config for SPA routing
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Step 2: Create azure.yaml**

Create `azure.yaml` at the project root:

```yaml
# MomentLoop Azure Developer CLI manifest
name: momentloop
metadata:
  template: momentloop

services:
  backend:
    host: containerapp
    language: python
    project: ./backend
    docker:
      path: ./backend/Dockerfile

  frontend:
    host: containerapp
    language: js
    project: ./frontend
    docker:
      path: ./frontend/Dockerfile.prod

infra:
  provider: bicep
  path: ./infra
```

**Step 3: Commit**

```bash
git add azure.yaml frontend/Dockerfile.prod
git commit -m "feat: add azure.yaml manifest and production frontend Dockerfile"
```

---

## Task 12: Create GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Step 1: Create deploy workflow**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Azure

on:
  push:
    branches: [master]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

env:
  AZURE_CONTAINER_REGISTRY: ${{ vars.AZURE_CONTAINER_REGISTRY }}
  BACKEND_IMAGE: momentloop-backend
  FRONTEND_IMAGE: momentloop-frontend

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Login to ACR
        run: az acr login --name ${{ env.AZURE_CONTAINER_REGISTRY }}

      - name: Build and push backend image
        run: |
          docker build -t ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.BACKEND_IMAGE }}:${{ github.sha }} \
                       -t ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.BACKEND_IMAGE }}:latest \
                       ./backend
          docker push ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.BACKEND_IMAGE }} --all-tags

      - name: Build and push frontend image
        run: |
          docker build -f ./frontend/Dockerfile.prod \
                       --build-arg VITE_API_URL=${{ vars.BACKEND_URL }} \
                       --build-arg VITE_GOOGLE_CLIENT_ID=${{ vars.GOOGLE_CLIENT_ID }} \
                       -t ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.FRONTEND_IMAGE }}:${{ github.sha }} \
                       -t ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.FRONTEND_IMAGE }}:latest \
                       ./frontend
          docker push ${{ env.AZURE_CONTAINER_REGISTRY }}.azurecr.io/${{ env.FRONTEND_IMAGE }} --all-tags

      - name: Install azd
        uses: Azure/setup-azd@v2

      - name: Deploy with azd
        run: azd deploy --no-prompt
        env:
          AZURE_ENV_NAME: ${{ vars.AZURE_ENV_NAME }}
          AZURE_LOCATION: ${{ vars.AZURE_LOCATION }}
          AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions deploy workflow for Azure"
```

---

## Task 13: Update .env.example and documentation

**Files:**
- Modify: `backend/.env.example` (if it exists at root, modify `.env.example`)

**Step 1: Update .env.example with Azure settings**

Add Azure-specific settings to `.env.example`:

```
# ============================================================
# Storage Backend: "local" (default) or "azure"
# ============================================================
STORAGE_BACKEND=local

# Azure Blob Storage (only when STORAGE_BACKEND=azure)
# AZURE_STORAGE_ACCOUNT_NAME=your-storage-account
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Azure storage settings to .env.example"
```

---

## Task 14: Google Cloud Console manual configuration

After deploying to Azure, you need to update your Google Cloud Console settings for OAuth to work with the new Azure URLs.

**Manual Steps (documented here, not automated):**

### Google Cloud Console (console.cloud.google.com)

1. **Go to** APIs & Services → Credentials → Your OAuth 2.0 Client ID

2. **Add Authorized JavaScript origins:**
   - `https://<your-frontend-app>.azurecontainerapps.io`
   - `https://<your-backend-app>.azurecontainerapps.io`
   - Keep existing: `http://localhost:5173`, `http://localhost:8000`

3. **Add Authorized redirect URIs:**
   - `https://<your-backend-app>.azurecontainerapps.io/api/auth/callback`
   - `https://<your-backend-app>.azurecontainerapps.io/api/auth/callback/photos`
   - Keep existing: `http://localhost:8000/api/auth/callback`, `http://localhost:8000/api/auth/callback/photos`

4. **Update `GOOGLE_REDIRECT_URI` env var** in Azure Container App to:
   `https://<your-backend-app>.azurecontainerapps.io/api/auth/callback`

5. **Update `VITE_GOOGLE_CLIENT_ID`** — this is baked into the frontend build, so it's passed as a build arg in the GitHub Actions workflow.

### Google AI Studio (aistudio.google.com)
- No changes needed — the API key works regardless of origin.

### fal.ai Dashboard
- No changes needed — the API key works regardless of origin.

---

## Task 15: Run full test suite and linting

**Step 1: Run linting**

Run: `cd backend && uv run ruff check . && uv run ruff format --check .`
Expected: No errors.

**Step 2: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: All tests pass.

**Step 3: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

---

## Summary of all files created/modified

### New files (infrastructure)
- `infra/main.bicep`
- `infra/main.bicepparam`
- `infra/abbreviations.json`
- `infra/modules/monitoring.bicep`
- `infra/modules/container-registry.bicep`
- `infra/modules/storage.bicep`
- `infra/modules/key-vault.bicep`
- `infra/modules/postgresql.bicep`
- `infra/modules/container-apps-env.bicep`
- `infra/modules/container-app-backend.bicep`
- `infra/modules/container-app-frontend.bicep`
- `azure.yaml`
- `frontend/Dockerfile.prod`
- `.github/workflows/deploy.yml`

### New files (backend code)
- `backend/app/services/azure_storage.py`
- `backend/app/api/routes/storage_proxy.py`
- `backend/tests/test_config.py`
- `backend/tests/test_storage.py`
- `backend/tests/test_azure_storage.py`

### Modified files
- `backend/pyproject.toml` — add azure optional deps
- `backend/app/core/config.py` — add storage_backend, azure settings
- `backend/app/services/storage.py` — refactor to LocalStorageBackend + factory
- `backend/app/main.py` — conditional StaticFiles vs proxy
- `.env.example` — add Azure settings

### NOT modified (zero changes)
- All database models
- All API route files (except main.py mount)
- All frontend code
- `docker-compose.yml`
- Existing tests
