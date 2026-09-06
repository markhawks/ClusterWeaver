"""track user password change time

Revision ID: 0009_password_changed
Revises: 0008_users
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_password_changed"
down_revision = "0008_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET password_changed_at = created_at WHERE password_changed_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
