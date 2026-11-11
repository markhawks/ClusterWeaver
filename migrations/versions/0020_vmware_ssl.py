"""Correct the mistakenly introduced HTTP transport to the requested SSL flags."""
from alembic import op
revision = '0020_vmware_ssl'
down_revision = '0019_vmware_transport'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM step_executions WHERE step IN ('08a', '08a-fa', '08b', '08c') AND project_id IN (SELECT project_id FROM stonith_configurations WHERE hardware = 'vmware' AND vmware_transport = 'http')")
    op.execute("UPDATE stonith_configurations SET vmware_transport = 'https_insecure' WHERE hardware = 'vmware' AND vmware_transport = 'http'")


def downgrade():
    pass
