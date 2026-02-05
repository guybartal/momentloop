"""Add prompt_generation_status to photos table

Revision ID: 007
Revises: 006
Create Date: 2024-01-28

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("prompt_generation_status", sa.String(20), nullable=False, server_default="pending")
    )
    # Set existing photos with prompts to 'completed'
    op.execute(
        "UPDATE photos SET prompt_generation_status = 'completed' WHERE animation_prompt IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("photos", "prompt_generation_status")
