"""add generated workflow execution results

Revision ID: 0007_step_results
Revises: 0006_node_ssh_bootstrap
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_step_results"
down_revision = "0006_node_ssh_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "step_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "node_id", "step", name="uq_step_execution_project_node_step"),
    )
    op.create_index("ix_step_executions_project_id", "step_executions", ["project_id"])
    op.create_index("ix_step_executions_node_id", "step_executions", ["node_id"])
    op.create_index("ix_step_executions_step", "step_executions", ["step"])


def downgrade() -> None:
    op.drop_table("step_executions")
