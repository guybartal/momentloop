"""Tests for storage service dual-mode backend."""

import uuid

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
        from app.services.storage import LocalStorageBackend, storage_service

        # Default config should create local backend
        assert isinstance(storage_service, LocalStorageBackend)
