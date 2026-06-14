"""Add audit logs and persistent rate-limit events."""

from alembic import op
import sqlalchemy as sa

revision = "20260614_0002"
down_revision = "20260614_0001"
branch_labels = None
depends_on = None


def has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not has_table("rate_limit_events"):
        op.create_table(
            "rate_limit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(255), nullable=False),
            sa.Column("scope", sa.String(50), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_rate_limit_events_key", "rate_limit_events", ["key"])
        op.create_index("ix_rate_limit_events_scope", "rate_limit_events", ["scope"])
        op.create_index("ix_rate_limit_events_created_at", "rate_limit_events", ["created_at"])

    if not has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=False),
            sa.Column("resource_id", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_status", "audit_logs", ["status"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    if has_table("audit_logs"):
        op.drop_table("audit_logs")
    if has_table("rate_limit_events"):
        op.drop_table("rate_limit_events")
