"""Add requirements column to features table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-07

Changes:
  features: add requirements JSON column for storing pip package requirements
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add requirements column to features
    op.add_column(
        "features",
        sa.Column("requirements", sa.JSON(), nullable=True, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("features", "requirements")
