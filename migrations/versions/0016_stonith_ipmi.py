"""Add direct iDRAC/IPMI definitions, preserving OEM configurations."""
from alembic import op
import sqlalchemy as sa
revision = "0016_stonith_ipmi"
down_revision = "0015_stonith_profiles"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("stonith_configurations", sa.Column("mode", sa.String(20), nullable=False, server_default="oem"))
    op.add_column("stonith_profiles", sa.Column("controller_endpoint", sa.String(253), nullable=False, server_default=""))
    op.add_column("stonith_profiles", sa.Column("resource_name", sa.String(160), nullable=False, server_default=""))

def downgrade():
    with op.batch_alter_table("stonith_profiles") as batch:
        batch.drop_column("resource_name")
        batch.drop_column("controller_endpoint")
    with op.batch_alter_table("stonith_configurations") as batch:
        batch.drop_column("mode")
