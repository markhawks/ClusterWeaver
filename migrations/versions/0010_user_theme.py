"""add per-user interface theme

Revision ID: 0010_user_theme
Revises: 0009_password_changed
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_user_theme"
down_revision = "0009_password_changed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme", sa.String(16), nullable=False, server_default="dark"))


def downgrade() -> None:
    op.drop_column("users", "theme")
