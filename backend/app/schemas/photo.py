import uuid
from datetime import datetime

from pydantic import BaseModel


class PhotoBase(BaseModel):
    position: int = 0


class PhotoCreate(PhotoBase):
    original_path: str


class PhotoUpdate(BaseModel):
    animation_prompt: str | None = None
    position: int | None = None


class PhotoResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_path: str
    original_url: str
    styled_path: str | None
    styled_url: str | None
    animation_prompt: str | None
    position: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class PhotoReorderRequest(BaseModel):
    photo_ids: list[uuid.UUID]
