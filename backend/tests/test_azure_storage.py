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
        mock_settings_obj = MagicMock()
        mock_settings_obj.storage_backend = "azure"
        mock_settings_obj.azure_storage_account_name = "testaccount"
        mock_settings_obj.storage_path = Path("/tmp/momentloop-test")
        with patch("app.services.azure_storage.settings", mock_settings_obj):
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
