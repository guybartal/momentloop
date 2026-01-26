import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.styled_variant import StyledVariant
    from app.models.video import Video


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    styled_path: Mapped[str | None] = mapped_column(Text)
    animation_prompt: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")  # uploaded, styled, ready
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="photos")
    video: Mapped["Video | None"] = relationship(
        "Video",
        back_populates="photo",
        foreign_keys="Video.photo_id",
        uselist=False,
    )
    variants: Mapped[list["StyledVariant"]] = relationship(
        "StyledVariant",
        back_populates="photo",
        cascade="all, delete-orphan",
        order_by="StyledVariant.created_at.desc()",
    )
