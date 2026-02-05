"""Add is_main field to exports table

Revision ID: 009
Revises: 008
Create Date: 2024-02-05

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exports", sa.Column("is_main", sa.Boolean(), nullable=False, server_default="false")
    )


def downgrade() -> None:
    op.drop_column("exports", "is_main")
