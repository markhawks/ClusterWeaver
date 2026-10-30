"""Persist encrypted controller credentials, separately from portable definitions."""
from alembic import op
import sqlalchemy as sa
revision = '0018_stonith_passwords'
down_revision = '0017_cluster_operations'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stonith_profiles', sa.Column('password_encrypted', sa.Text(), nullable=False, server_default=''))


def downgrade():
    with op.batch_alter_table('stonith_profiles') as batch:
        batch.drop_column('password_encrypted')
