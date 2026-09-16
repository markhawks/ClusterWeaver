"""add mandatory initial password change flag

Revision ID: 0014_user_password_change
Revises: 0013_project_groups
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_user_password_change"
down_revision = "0013_project_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("must_change_password")
