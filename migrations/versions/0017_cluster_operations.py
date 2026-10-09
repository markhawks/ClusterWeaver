"""Persist background cluster operations and reserve one active job per project."""
from alembic import op
import sqlalchemy as sa
revision = '0017_cluster_operations'
down_revision = '0016_stonith_ipmi'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('cluster_operations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('active_project_id', sa.Integer(), nullable=True, unique=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('target_node', sa.String(253), nullable=False),
        sa.Column('username', sa.String(128), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('phase', sa.String(80), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('results', sa.JSON(), nullable=False))
    op.create_index('ix_cluster_operations_project_id', 'cluster_operations', ['project_id'])

def downgrade():
    op.drop_table('cluster_operations')
