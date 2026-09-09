"""add project cluster name

Revision ID: 0012_project_cluster_name
Revises: 0011_project_hardware
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_project_cluster_name"
down_revision = "0011_project_hardware"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("cluster_name", sa.String(64), nullable=False, server_default=""))
    op.execute("UPDATE projects SET cluster_name = slug WHERE cluster_name = ''")


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("cluster_name")
