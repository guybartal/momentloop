from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "MomentLoop"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://momentloop:momentloop@localhost:5432/momentloop"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # Google AI (Imagen)
    google_ai_api_key: str = ""

    # fal.ai
    fal_key: str = ""

    # JWT
    jwt_secret: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # Storage
    storage_path: Path = Path("./storage")

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def uploads_path(self) -> Path:
        return self.storage_path / "uploads"

    @property
    def styled_path(self) -> Path:
        return self.storage_path / "styled"

    @property
    def videos_path(self) -> Path:
        return self.storage_path / "videos"

    @property
    def exports_path(self) -> Path:
        return self.storage_path / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
