"""Baseline existing schema and add persistent processing tasks."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260614_0001"
down_revision = None
branch_labels = None
depends_on = None


def has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def columns(name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if not has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"])

    if not has_table("knowledge_bases"):
        op.create_table(
            "knowledge_bases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_knowledge_bases_user_id", "knowledge_bases", ["user_id"])

    if not has_table("documents"):
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "knowledge_base_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_bases.id"),
                nullable=False,
            ),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])

    if not has_table("document_chunks"):
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("section_title", sa.String(300), nullable=False, server_default=""),
            sa.Column("char_start", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("char_end", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_type", sa.String(30), nullable=False, server_default="body"),
        )
        op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    else:
        existing = columns("document_chunks")
        additions = {
            "section_title": sa.Column(
                "section_title", sa.String(300), nullable=False, server_default=""
            ),
            "char_start": sa.Column("char_start", sa.Integer(), nullable=False, server_default="0"),
            "char_end": sa.Column("char_end", sa.Integer(), nullable=False, server_default="0"),
            "content_type": sa.Column(
                "content_type", sa.String(30), nullable=False, server_default="body"
            ),
        }
        for name, column in additions.items():
            if name not in existing:
                op.add_column("document_chunks", column)

    if not has_table("chunk_embeddings"):
        op.create_table(
            "chunk_embeddings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=False
            ),
            sa.Column("vector_json", sa.Text(), nullable=False),
            sa.Column("vector", Vector(512), nullable=True),
            sa.Column("model", sa.String(120), nullable=False),
            sa.UniqueConstraint("chunk_id"),
        )
        op.create_index("ix_chunk_embeddings_chunk_id", "chunk_embeddings", ["chunk_id"])
    elif "vector" not in columns("chunk_embeddings"):
        op.add_column("chunk_embeddings", sa.Column("vector", Vector(512), nullable=True))

    if not has_table("chat_sessions"):
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "knowledge_base_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_bases.id"),
                nullable=False,
            ),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
        op.create_index("ix_chat_sessions_knowledge_base_id", "chat_sessions", ["knowledge_base_id"])

    if not has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False
            ),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    if not has_table("processing_tasks"):
        op.create_table(
            "processing_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("task_type", sa.String(50), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("available_at", sa.DateTime(), nullable=False),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_processing_tasks_document_id", "processing_tasks", ["document_id"])
        op.create_index("ix_processing_tasks_status", "processing_tasks", ["status"])
        op.create_index("ix_processing_tasks_available_at", "processing_tasks", ["available_at"])


def downgrade() -> None:
    if has_table("processing_tasks"):
        op.drop_table("processing_tasks")
