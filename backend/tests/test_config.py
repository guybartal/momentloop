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
