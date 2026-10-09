"""Add step 08a OEM configuration and credential-free profile definitions."""

from alembic import op
import sqlalchemy as sa

revision = "0015_stonith_profiles"
down_revision = "0014_user_password_change"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stonith_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("hardware", sa.String(20), nullable=False),
        sa.Column("endpoint", sa.String(253), nullable=False),
    )
    op.create_table(
        "stonith_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("stonith_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("profile_name", sa.String(160), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stonith_profiles")
    op.drop_table("stonith_configurations")
