"""add project hardware

Revision ID: 0011_project_hardware
Revises: 0010_user_theme
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_project_hardware"
down_revision = "0010_user_theme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("hardware", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("hardware")
