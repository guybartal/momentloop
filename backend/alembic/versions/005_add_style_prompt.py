"""Add style_prompt to projects table

Revision ID: 005
Revises: 004
Create Date: 2024-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("style_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "style_prompt")
