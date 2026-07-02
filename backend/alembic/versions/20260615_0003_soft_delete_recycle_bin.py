"""Add soft-delete retention fields."""

from alembic import op
import sqlalchemy as sa

revision = "20260615_0003"
down_revision = "20260614_0002"
branch_labels = None
depends_on = None

TABLES = ("knowledge_bases", "documents", "document_chunks", "chunk_embeddings")


def columns(name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    for table in TABLES:
        existing = columns(table)
        if "deleted_at" not in existing:
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
            op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])
        if "purge_after" not in existing:
            op.add_column(table, sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True))
            op.create_index(f"ix_{table}_purge_after", table, ["purge_after"])
        if "deleted_by_user_id" not in existing:
            foreign_key = (
                sa.ForeignKey("users.id", ondelete="SET NULL")
                if op.get_bind().dialect.name != "sqlite"
                else None
            )
            op.add_column(
                table,
                sa.Column(
                    "deleted_by_user_id",
                    sa.Integer(),
                    foreign_key,
                    nullable=True,
                ),
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "deleted_by_user_id")
        op.drop_index(f"ix_{table}_purge_after", table_name=table)
        op.drop_column(table, "purge_after")
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_column(table, "deleted_at")
