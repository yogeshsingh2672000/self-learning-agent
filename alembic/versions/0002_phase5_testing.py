"""Phase 5 – Testing Agent additions

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

Changes:
  tasks:    add escalation_reason TEXT column (nullable)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add escalation_reason to tasks
    op.add_column(
        "tasks",
        sa.Column("escalation_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "escalation_reason")
