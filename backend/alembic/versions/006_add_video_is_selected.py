"""Add is_selected to videos table

Revision ID: 006
Revises: 005
Create Date: 2024-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("is_selected", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("videos", "is_selected")
