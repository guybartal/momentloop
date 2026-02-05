"""Move style from photos to projects

Revision ID: 002
Revises: 001
Create Date: 2024-01-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add style column to projects table
    op.add_column("projects", sa.Column("style", sa.String(50), nullable=True))

    # Drop style column from photos table
    op.drop_column("photos", "style")


def downgrade() -> None:
    # Add style column back to photos table
    op.add_column("photos", sa.Column("style", sa.String(50), nullable=True))

    # Drop style column from projects table
    op.drop_column("projects", "style")
