"""Phase 6 – PR columns for features table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07

Changes:
  features: add pr_number INT and pr_status VARCHAR(50) columns (nullable)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add pr_number and pr_status to features
    op.add_column(
        "features",
        sa.Column("pr_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "features",
        sa.Column("pr_status", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("features", "pr_status")
    op.drop_column("features", "pr_number")
