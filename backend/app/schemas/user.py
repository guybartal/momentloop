import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    name: str | None = None


class UserCreate(UserBase):
    google_id: str
    avatar_url: str | None = None


class UserResponse(UserBase):
    id: uuid.UUID
    avatar_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleUserInfo(BaseModel):
    id: str
    email: str
    name: str | None = None
    picture: str | None = None
