"""Mentoria workshop registration table (additive, tenant-bound, no backfill).

Deployment order: source compatibility -> migration in approved staging -> feature flag.
Downgrade stops on any retained lead, to prevent silent PII loss.
"""
from alembic import op
import sqlalchemy as sa

revision = "017_mentoria_workshop"
down_revision = "016_thread_participant_access_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("mentoria_workshop_registrations"):
        raise RuntimeError("STOP_MENTORIA_TABLE_ALREADY_EXISTS")
    op.create_table(
        "mentoria_workshop_registrations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("workshop_slug", sa.String(80), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("company_name", sa.String(160), nullable=True),
        sa.Column("privacy_notice_version", sa.String(40), nullable=False),
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT",
                                name="fk_mentoria_workshop_tenant"),
        sa.UniqueConstraint("tenant_id", "workshop_slug", "email_normalized",
                            name="uq_mentoria_workshop_email"),
        sa.CheckConstraint("length(email_normalized) > 3",
                           name="ck_mentoria_workshop_email_not_empty"),
    )
    op.create_index("ix_mentoria_workshop_registrations_tenant_id",
                    "mentoria_workshop_registrations", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM mentoria_workshop_registrations LIMIT 1)"
    )).scalar():
        raise RuntimeError("STOP_MENTORIA_DOWNGRADE_DATA_PRESENT")
    op.drop_index("ix_mentoria_workshop_registrations_tenant_id",
                  table_name="mentoria_workshop_registrations")
    op.drop_table("mentoria_workshop_registrations")
