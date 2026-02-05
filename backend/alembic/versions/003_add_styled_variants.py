"""Add styled variants table

Revision ID: 003
Revises: 002
Create Date: 2024-01-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create styled_variants table
    op.create_table(
        "styled_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "photo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("styled_path", sa.Text(), nullable=False),
        sa.Column("style", sa.String(50), nullable=False),
        sa.Column("is_selected", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create index for faster lookups
    op.create_index("ix_styled_variants_photo_id", "styled_variants", ["photo_id"])


def downgrade() -> None:
    op.drop_index("ix_styled_variants_photo_id")
    op.drop_table("styled_variants")
