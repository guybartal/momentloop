import uuid
from datetime import datetime

from pydantic import BaseModel


class VideoBase(BaseModel):
    prompt: str | None = None


class VideoCreate(VideoBase):
    photo_id: uuid.UUID | None = None
    video_type: str = "scene"  # scene or transition
    source_photo_id: uuid.UUID | None = None
    target_photo_id: uuid.UUID | None = None


class VideoResponse(BaseModel):
    id: uuid.UUID
    photo_id: uuid.UUID | None
    project_id: uuid.UUID
    video_path: str | None
    video_url: str | None
    video_type: str
    source_photo_id: uuid.UUID | None
    target_photo_id: uuid.UUID | None
    prompt: str | None
    duration_seconds: float | None
    position: int | None
    status: str
    is_selected: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SelectVideoRequest(BaseModel):
    video_id: uuid.UUID


class GenerateVideoRequest(BaseModel):
    prompt: str | None = None  # Optional override for photo's animation_prompt


class TransitionVideoRequest(BaseModel):
    source_photo_id: uuid.UUID
    target_photo_id: uuid.UUID
    prompt: str | None = None
