"""Add Google OAuth tokens to users table

Revision ID: 004
Revises: 003
Create Date: 2024-01-26

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_access_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("google_refresh_token", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "google_token_expiry",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "google_token_expiry")
    op.drop_column("users", "google_refresh_token")
    op.drop_column("users", "google_access_token")
