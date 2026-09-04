"""Add primary and secondary node interface names."""
from alembic import op
import sqlalchemy as sa


revision = "0002_node_interfaces"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(sa.Column("primary_interface", sa.String(64), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("secondary_interface", sa.String(64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("secondary_interface")
        batch_op.drop_column("primary_interface")
