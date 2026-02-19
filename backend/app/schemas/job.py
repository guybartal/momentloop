import uuid
from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    project_id: uuid.UUID
    job_type: str
    description: str


class JobResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    description: str
    status: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True
