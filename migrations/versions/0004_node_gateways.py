"""add node gateways

Revision ID: 0004_node_gateways
Revises: 0003_node_nodename
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_node_gateways"
down_revision = "0003_node_nodename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(sa.Column("management_gateway", sa.String(45), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("cluster_gateway", sa.String(45), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("cluster_gateway")
        batch_op.drop_column("management_gateway")
