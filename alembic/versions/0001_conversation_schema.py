"""Create production conversation schema.

Revision ID: 0001_conversation_schema
Revises:
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_conversation_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("last_message_summary", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "external_id", name="uq_conversations_user_external_id"),
    )
    op.create_index("idx_conversations_user_updated_at", "conversations", ["user_id", "updated_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_conversation_id_id", "messages", ["conversation_id", "id"])
    op.create_index("idx_messages_user_created_at", "messages", ["user_id", "created_at"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("storage_uri", sa.String(length=500), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_conversation_id", "documents", ["conversation_id"])
    op.create_index("idx_documents_user_created_at", "documents", ["user_id", "created_at"])
    op.create_table(
        "tool_call_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tool_call_logs_conversation_created_at", "tool_call_logs", ["conversation_id", "created_at"])
    op.create_index("idx_tool_call_logs_user_created_at", "tool_call_logs", ["user_id", "created_at"])
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.String(length=120), nullable=True),
        sa.Column("step", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_traces_conversation_created_at", "agent_traces", ["conversation_id", "created_at"])
    op.create_index("idx_agent_traces_trace_id", "agent_traces", ["trace_id"])
    op.create_index("idx_agent_traces_user_created_at", "agent_traces", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_traces_user_created_at", table_name="agent_traces")
    op.drop_index("idx_agent_traces_trace_id", table_name="agent_traces")
    op.drop_index("idx_agent_traces_conversation_created_at", table_name="agent_traces")
    op.drop_table("agent_traces")
    op.drop_index("idx_tool_call_logs_user_created_at", table_name="tool_call_logs")
    op.drop_index("idx_tool_call_logs_conversation_created_at", table_name="tool_call_logs")
    op.drop_table("tool_call_logs")
    op.drop_index("idx_documents_user_created_at", table_name="documents")
    op.drop_index("idx_documents_conversation_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("idx_messages_user_created_at", table_name="messages")
    op.drop_index("idx_messages_conversation_id_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_user_updated_at", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("users")
