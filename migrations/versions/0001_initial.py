"""Create projects and nodes tables."""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("customer", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rhel_major", sa.Integer(), nullable=False),
        sa.Column("rhel_minor", sa.String(20), nullable=False),
        sa.Column("platform_type", sa.String(20), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)
    op.create_index("ix_projects_customer", "projects", ["customer"])
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("fqdn", sa.String(253), nullable=False),
        sa.Column("site", sa.String(120), nullable=False),
        sa.Column("management_ip", sa.String(45), nullable=False),
        sa.Column("cluster_ip", sa.String(45), nullable=False),
        sa.UniqueConstraint("project_id", "hostname", name="uq_node_project_hostname"),
    )
    op.create_index("ix_nodes_project_id", "nodes", ["project_id"])


def downgrade() -> None:
    op.drop_table("nodes")
    op.drop_table("projects")
