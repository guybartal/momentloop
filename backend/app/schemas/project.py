import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    style: str | None = None
    style_prompt: str | None = None
    status: str | None = None


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    user_id: uuid.UUID
    style: str | None
    style_prompt: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    id: uuid.UUID
    name: str
    style: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    photo_count: int = 0
    thumbnail_url: str | None = None

    class Config:
        from_attributes = True
