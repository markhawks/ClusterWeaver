"""add node ssh bootstrap endpoint

Revision ID: 0006_node_ssh_bootstrap
Revises: 0005_project_hypervisor
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_node_ssh_bootstrap"
down_revision = "0005_project_hypervisor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(sa.Column("bootstrap_ip", sa.String(45), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"))


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("ssh_port")
        batch_op.drop_column("bootstrap_ip")
