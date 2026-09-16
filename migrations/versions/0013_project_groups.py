"""add project groups

Revision ID: 0013_project_groups
Revises: 0012_project_cluster_name
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_project_groups"
down_revision = "0012_project_cluster_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_project_groups_normalized_name"), "project_groups", ["normalized_name"], unique=True)
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_projects_group_id"), ["group_id"], unique=False)
        batch_op.create_foreign_key("fk_projects_group_id_project_groups", "project_groups", ["group_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("fk_projects_group_id_project_groups", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_projects_group_id"))
        batch_op.drop_column("group_id")
    op.drop_index(op.f("ix_project_groups_normalized_name"), table_name="project_groups")
    op.drop_table("project_groups")
