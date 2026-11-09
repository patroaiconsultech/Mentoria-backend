"""M2-C2B durable Asaas notification ingress; PROPOSAL ONLY.

Additive; reconcile HEAD, migration chain and PostgreSQL before use.
No DDL on operational database without separate approval.
"""
from alembic import op
import sqlalchemy as sa

revision = "019_mentoria_webhook_inbox"
down_revision = "018_mentoria_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("mentoria_webhook_inbox"):
        raise RuntimeError("STOP_MENTORIA_019_EXISTING_TABLE")
    op.create_table(
        "mentoria_webhook_inbox",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=False),
        sa.Column("payment_attempt_id", sa.String(64), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("event_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(60), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payment_attempt_id", "provider"],
            ["mentoria_payment_attempts.tenant_id", "mentoria_payment_attempts.id",
             "mentoria_payment_attempts.provider"],
            ondelete="RESTRICT", name="fk_mt_inbox_attempt_provider",
        ),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_mt_inbox_event"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_mt_inbox_attempts"),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','RETRY','REVIEW','PROCESSED')",
            name="ck_mt_inbox_status",
        ),
    )
    op.create_index("ix_mt_inbox_schedule", "mentoria_webhook_inbox",
                    ["status", "next_attempt_at"])
    op.create_index("ix_mt_inbox_tenant_received", "mentoria_webhook_inbox",
                    ["tenant_id", "received_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("mentoria_webhook_inbox"):
        raise RuntimeError("STOP_MENTORIA_019_TABLE_MISSING")
    count = bind.execute(sa.text("SELECT COUNT(*) FROM mentoria_webhook_inbox")).scalar_one()
    if count:
        raise RuntimeError("STOP_MENTORIA_019_HAS_DURABLE_RECEIPTS")
    op.drop_index("ix_mt_inbox_tenant_received", table_name="mentoria_webhook_inbox")
    op.drop_index("ix_mt_inbox_schedule", table_name="mentoria_webhook_inbox")
    op.drop_table("mentoria_webhook_inbox")
