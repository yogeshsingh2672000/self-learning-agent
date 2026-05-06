"""initial schema – all tables

Revision ID: 0001
Revises:
Create Date: 2026-05-06

Covers:
  users, tasks, features, approval_logs, agent_logs, tool_registry_db, chat_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types (idempotent DO blocks) ─────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE taskstatus AS ENUM (
                'pending_approval', 'approved', 'in_development',
                'testing', 'in_review', 'deployed', 'rejected', 'escalated'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE featurestatus AS ENUM (
                'development', 'testing', 'in_review', 'deployed', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE approvaldecision AS ENUM ('approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE agenttype AS ENUM (
                'query', 'task_manager', 'coding', 'testing'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE agentlogstatus AS ENUM (
                'success', 'failure', 'in_progress'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagerole AS ENUM ('user', 'agent', 'system');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── tasks ─────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="taskstatus", create_type=False), nullable=False,
                  server_default="pending_approval"),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("required_capabilities", postgresql.JSON(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── features ──────────────────────────────────────────────────────────────
    op.create_table(
        "features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("tool_code", sa.Text(), nullable=True),
        sa.Column("test_code", sa.Text(), nullable=True),
        sa.Column("test_results", postgresql.JSON(), nullable=True),
        sa.Column("pr_url", sa.String(500), nullable=True),
        sa.Column("status", postgresql.ENUM(name="featurestatus", create_type=False), nullable=False,
                  server_default="development"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_features_task_id", "features", ["task_id"])

    # ── approval_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "approval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("approver", sa.String(255), nullable=False),
        sa.Column("decision", postgresql.ENUM(name="approvaldecision", create_type=False), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approval_logs_task_id", "approval_logs", ["task_id"])

    # ── agent_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "agent_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_type", postgresql.ENUM(name="agenttype", create_type=False), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("action", sa.String(500), nullable=False),
        sa.Column("details", postgresql.JSON(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="agentlogstatus", create_type=False), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_logs_task_id", "agent_logs", ["task_id"])

    # ── tool_registry_db ──────────────────────────────────────────────────────
    op.create_table(
        "tool_registry_db",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tool_name", sa.String(255), nullable=False, unique=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_registry_db_tool_name", "tool_registry_db", ["tool_name"])

    # ── chat_history ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="messagerole", create_type=False), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_capability_gap", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("gap_description", sa.Text(), nullable=True),
        sa.Column("suggested_tool", sa.String(500), nullable=True),
        sa.Column("message_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_history_user_id", "chat_history", ["user_id"])
    op.create_index("ix_chat_history_session_id", "chat_history", ["session_id"])


def downgrade() -> None:
    op.drop_table("chat_history")
    op.drop_table("tool_registry_db")
    op.drop_table("agent_logs")
    op.drop_table("approval_logs")
    op.drop_table("features")
    op.drop_table("tasks")
    op.drop_table("users")

    # Drop enum types
    for enum_name in [
        "messagerole", "agentlogstatus", "agenttype",
        "approvaldecision", "featurestatus", "taskstatus",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
