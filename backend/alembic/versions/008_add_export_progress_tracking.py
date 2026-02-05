"""Add progress tracking fields to exports table

Revision ID: 008
Revises: 007
Create Date: 2024-02-05

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exports",
        sa.Column("thumbnail_path", sa.Text(), nullable=True)
    )
    op.add_column(
        "exports",
        sa.Column("progress_step", sa.String(50), nullable=True)
    )
    op.add_column(
        "exports",
        sa.Column("progress_detail", sa.Text(), nullable=True)
    )
    op.add_column(
        "exports",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "exports",
        sa.Column("error_message", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("exports", "error_message")
    op.drop_column("exports", "progress_percent")
    op.drop_column("exports", "progress_detail")
    op.drop_column("exports", "progress_step")
    op.drop_column("exports", "thumbnail_path")
