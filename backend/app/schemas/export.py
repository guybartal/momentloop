import uuid
from datetime import datetime

from pydantic import BaseModel


class ExportCreate(BaseModel):
    include_transitions: bool = True


class ExportResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    file_path: str | None
    file_url: str | None
    thumbnail_path: str | None
    thumbnail_url: str | None
    status: str
    progress_step: str | None
    progress_detail: str | None
    progress_percent: int = 0
    error_message: str | None
    is_main: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ExportStatusResponse(BaseModel):
    export_id: str
    status: str
    file_url: str | None
    thumbnail_url: str | None
    progress: int = 0  # 0-100
    progress_step: str | None
    progress_detail: str | None
    error_message: str | None
