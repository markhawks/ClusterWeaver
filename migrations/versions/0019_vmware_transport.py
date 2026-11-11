"""Persist explicit VMware HTTP/HTTPS and certificate verification settings."""
from alembic import op
import sqlalchemy as sa
revision = '0019_vmware_transport'
down_revision = '0018_stonith_passwords'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stonith_configurations', sa.Column('vmware_transport', sa.String(20), nullable=False, server_default='https_secure'))


def downgrade():
    with op.batch_alter_table('stonith_configurations') as batch:
        batch.drop_column('vmware_transport')
