from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    log_level: str = "INFO"

    # Rate limiting
    rate_limit_auth: str = "10/minute"
    rate_limit_api: str = "100/minute"

    # Concurrency limits
    max_concurrent_style_transfers: int = 3
    max_concurrent_video_generations: int = 5
    max_concurrent_exports: int = 2

    # File retention (days)
    export_retention_days: int = 7
    orphan_cleanup_enabled: bool = True

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

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters for security")
        return v

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
