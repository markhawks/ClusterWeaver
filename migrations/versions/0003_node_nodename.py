"""Add the cluster node name."""
from alembic import op
import sqlalchemy as sa

revision = "0003_node_nodename"
down_revision = "0002_node_interfaces"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.add_column(sa.Column("nodename", sa.String(253), nullable=False, server_default=""))
    op.execute("UPDATE nodes SET nodename = hostname || 'lanc' WHERE nodename = ''")

def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("nodename")
