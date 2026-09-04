"""add project hypervisor

Revision ID: 0005_project_hypervisor
Revises: 0004_node_gateways
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_project_hypervisor"
down_revision = "0004_node_gateways"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("hypervisor", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("hypervisor")
