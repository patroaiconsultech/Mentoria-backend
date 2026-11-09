"""M2-B Mentoria core schema (additive, no backfill, no access enabled).

SOURCE_PROPOSAL_ONLY: derived from ZIP staging + M1 proposal, NOT from pinned Git HEAD.
Preflight must reconcile this down_revision with official Alembic before application.
"""
from alembic import op
import sqlalchemy as sa

revision = "018_mentoria_core"
down_revision = "017_mentoria_workshop"
branch_labels = None
depends_on = None

M2B_TABLE_NAMES = ('mentoria_programs', 'mentoria_cohorts', 'mentoria_offers', 'mentoria_members', 'mentoria_orders', 'mentoria_payment_attempts', 'mentoria_provider_events', 'mentoria_seat_holds', 'mentoria_enrollments', 'mentoria_access_grants', 'mentoria_audit_events', 'mentoria_outbox')

def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    present = [name for name in M2B_TABLE_NAMES if inspector.has_table(name)]
    if present:
        raise RuntimeError("STOP_MENTORIA_018_EXISTING_TABLES: " + ",".join(present))
    op.create_table('mentoria_programs',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('slug', sa.String(100), nullable=False, primary_key=False),
        sa.Column('title', sa.String(200), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name='ck_mt_program_status'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_program_identity'),
        sa.UniqueConstraint('tenant_id', 'slug', name='uq_mt_program_slug'),
    )
    op.create_table('mentoria_cohorts',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('program_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('capacity', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('timezone_name', sa.String(80), nullable=False, primary_key=False),
        sa.Column('registration_opens_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('registration_closes_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint('capacity > 0', name='ck_mt_cohort_capacity'),
        sa.CheckConstraint('ends_at > starts_at', name='ck_mt_cohort_dates'),
        sa.CheckConstraint('registration_closes_at > registration_opens_at', name='ck_mt_cohort_reg_window'),
        sa.CheckConstraint("status IN ('DRAFT', 'OPEN', 'CLOSED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name='ck_mt_cohort_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'program_id'], ['mentoria_programs.tenant_id', 'mentoria_programs.id'], name='fk_mt_cohort_program', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_cohort_identity'),
        sa.UniqueConstraint('tenant_id', 'id', 'program_id', name='uq_mt_cohort_program'),
    )
    op.create_table('mentoria_offers',
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=True),
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('cohort_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('program_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(3), nullable=False, primary_key=False),
        sa.Column('access_days', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('terms_version', sa.String(40), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint('access_days > 0', name='ck_mt_offer_access'),
        sa.CheckConstraint('amount_cents > 0', name='ck_mt_offer_amount'),
        sa.CheckConstraint("currency = 'BRL'", name='ck_mt_offer_currency'),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'RETIRED')", name='ck_mt_offer_status'),
        sa.CheckConstraint('version > 0', name='ck_mt_offer_version'),
        sa.ForeignKeyConstraint(['tenant_id', 'cohort_id', 'program_id'], ['mentoria_cohorts.tenant_id', 'mentoria_cohorts.id', 'mentoria_cohorts.program_id'], name='fk_mt_offer_cohort_program', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'cohort_id', 'id', 'version', name='uq_mt_offer_cohort_version'),
    )
    op.create_table('mentoria_members',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('issuer', sa.String(255), nullable=False, primary_key=False),
        sa.Column('subject', sa.String(255), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')", name='ck_mt_member_status'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_member_identity'),
        sa.UniqueConstraint('tenant_id', 'issuer', 'subject', name='uq_mt_member_subject'),
    )
    op.create_table('mentoria_orders',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('member_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('cohort_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('offer_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('offer_version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False, primary_key=False),
        sa.Column('currency', sa.String(3), nullable=False, primary_key=False),
        sa.Column('financial_state', sa.String(30), nullable=False, primary_key=False),
        sa.Column('fulfillment_state', sa.String(30), nullable=False, primary_key=False),
        sa.Column('idempotency_key_hash', sa.String(64), nullable=False, primary_key=False),
        sa.Column('request_fingerprint', sa.String(64), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint('amount_cents > 0', name='ck_mt_order_amount'),
        sa.CheckConstraint("currency = 'BRL'", name='ck_mt_order_currency'),
        sa.CheckConstraint("financial_state IN ('CREATED', 'AWAITING_PAYMENT', 'PAID', 'REVIEW_REQUIRED', 'REFUNDED', 'DISPUTED', 'CHARGEBACK', 'CANCELLED', 'EXPIRED')", name='ck_mt_order_financial'),
        sa.CheckConstraint("fulfillment_state IN ('PENDING', 'PAID_UNPLACED', 'ENROLLED', 'SUSPENDED', 'CLOSED')", name='ck_mt_order_fulfillment'),
        sa.ForeignKeyConstraint(['tenant_id', 'member_id'], ['mentoria_members.tenant_id', 'mentoria_members.id'], name='fk_mt_order_member', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id', 'cohort_id', 'offer_id', 'offer_version'], ['mentoria_offers.tenant_id', 'mentoria_offers.cohort_id', 'mentoria_offers.id', 'mentoria_offers.version'], name='fk_mt_order_offer', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'id', 'cohort_id', name='uq_mt_order_cohort'),
        sa.UniqueConstraint('tenant_id', 'member_id', 'idempotency_key_hash', name='uq_mt_order_idempotency'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_order_identity'),
        sa.UniqueConstraint('tenant_id', 'id', 'cohort_id', 'member_id', name='uq_mt_order_placement'),
    )
    op.create_index('ix_mt_orders_tenant_financial', 'mentoria_orders', ['tenant_id', 'financial_state'], unique=False)
    op.create_table('mentoria_payment_attempts',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('order_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('provider', sa.String(40), nullable=False, primary_key=False),
        sa.Column('provider_payment_id', sa.String(128), nullable=True, primary_key=False),
        sa.Column('external_reference', sa.String(128), nullable=False, primary_key=False),
        sa.Column('operation_state', sa.String(20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("operation_state IN ('NOT_STARTED', 'CALL_STARTED', 'BOUND', 'UNKNOWN', 'FAILED')", name='ck_mt_attempt_operation'),
        sa.CheckConstraint("provider <> ''", name='ck_mt_attempt_provider_not_empty'),
        sa.ForeignKeyConstraint(['tenant_id', 'order_id'], ['mentoria_orders.tenant_id', 'mentoria_orders.id'], name='fk_mt_attempt_order', ondelete='RESTRICT'),
        sa.UniqueConstraint('provider', 'external_reference', name='uq_mt_attempt_external_ref'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_attempt_identity'),
        sa.UniqueConstraint('tenant_id', 'id', 'provider', name='uq_mt_attempt_provider'),
    )
    op.create_index('uq_mt_attempt_provider_payment_id', 'mentoria_payment_attempts', ['provider', 'provider_payment_id'], unique=True, postgresql_where=sa.text('provider_payment_id IS NOT NULL'))
    op.create_table('mentoria_provider_events',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('provider', sa.String(40), nullable=False, primary_key=False),
        sa.Column('provider_event_id', sa.String(128), nullable=False, primary_key=False),
        sa.Column('payment_attempt_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('fact_type', sa.String(40), nullable=False, primary_key=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.CheckConstraint("provider_event_id <> ''", name='ck_mt_event_id_not_empty'),
        sa.ForeignKeyConstraint(['tenant_id', 'payment_attempt_id', 'provider'], ['mentoria_payment_attempts.tenant_id', 'mentoria_payment_attempts.id', 'mentoria_payment_attempts.provider'], name='fk_mt_event_attempt_provider', ondelete='RESTRICT'),
        sa.UniqueConstraint('provider', 'provider_event_id', name='uq_mt_event_provider_id'),
    )
    op.create_index('ix_mt_event_tenant_received', 'mentoria_provider_events', ['tenant_id', 'received_at'], unique=False)
    op.create_table('mentoria_seat_holds',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('order_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('cohort_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'CONSUMED', 'EXPIRED', 'RELEASED')", name='ck_mt_hold_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'order_id', 'cohort_id'], ['mentoria_orders.tenant_id', 'mentoria_orders.id', 'mentoria_orders.cohort_id'], name='fk_mt_hold_order_cohort', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'order_id', name='uq_mt_hold_order'),
    )
    op.create_index('ix_mt_hold_tenant_cohort_status_exp', 'mentoria_seat_holds', ['tenant_id', 'cohort_id', 'status', 'expires_at'], unique=False)
    op.create_table('mentoria_enrollments',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('order_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('cohort_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('member_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'CANCELLED')", name='ck_mt_enrollment_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'order_id', 'cohort_id', 'member_id'], ['mentoria_orders.tenant_id', 'mentoria_orders.id', 'mentoria_orders.cohort_id', 'mentoria_orders.member_id'], name='fk_mt_enrollment_order_binding', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'id', name='uq_mt_enrollment_identity'),
        sa.UniqueConstraint('tenant_id', 'cohort_id', 'member_id', name='uq_mt_enrollment_member'),
        sa.UniqueConstraint('tenant_id', 'order_id', name='uq_mt_enrollment_order'),
    )
    op.create_index('ix_mt_enrollment_tenant_cohort_status', 'mentoria_enrollments', ['tenant_id', 'cohort_id', 'status'], unique=False)
    op.create_table('mentoria_access_grants',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('enrollment_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.CheckConstraint("status <> 'ACTIVE' OR revoked_at IS NULL", name='ck_mt_grant_active_not_revoked'),
        sa.CheckConstraint('expires_at > starts_at', name='ck_mt_grant_dates'),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'REVOKED', 'EXPIRED')", name='ck_mt_grant_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'enrollment_id'], ['mentoria_enrollments.tenant_id', 'mentoria_enrollments.id'], name='fk_mt_grant_enrollment', ondelete='RESTRICT'),
        sa.UniqueConstraint('tenant_id', 'enrollment_id', name='uq_mt_grant_enrollment'),
    )
    op.create_table('mentoria_audit_events',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('actor_type', sa.String(30), nullable=False, primary_key=False),
        sa.Column('actor_id', sa.String(128), nullable=False, primary_key=False),
        sa.Column('request_id', sa.String(128), nullable=False, primary_key=False),
        sa.Column('action', sa.String(80), nullable=False, primary_key=False),
        sa.Column('resource_type', sa.String(80), nullable=False, primary_key=False),
        sa.Column('resource_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('metadata_whitelist', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_mt_audit_tenant_at', 'mentoria_audit_events', ['tenant_id', 'occurred_at'], unique=False)
    op.create_table('mentoria_outbox',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.String(64), sa.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, primary_key=False),
        sa.Column('event_key', sa.String(128), nullable=False, primary_key=False),
        sa.Column('event_type', sa.String(80), nullable=False, primary_key=False),
        sa.Column('aggregate_id', sa.String(64), nullable=False, primary_key=False),
        sa.Column('payload_whitelist', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(20), nullable=False, primary_key=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.CheckConstraint('attempt_count >= 0', name='ck_mt_outbox_attempt_count'),
        sa.CheckConstraint("status IN ('PENDING', 'CLAIMED', 'DELIVERED', 'FAILED')", name='ck_mt_outbox_status'),
        sa.UniqueConstraint('tenant_id', 'event_key', name='uq_mt_outbox_key'),
    )
    op.create_index('ix_mt_outbox_tenant_status_next', 'mentoria_outbox', ['tenant_id', 'status', 'next_attempt_at'], unique=False)

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing = [name for name in M2B_TABLE_NAMES if not inspector.has_table(name)]
    if missing:
        raise RuntimeError("STOP_MENTORIA_018_DOWNGRADE_MISSING_TABLES")
    # Check ALL tables before dropping ANY, including finance/audit/outbox.
    for name in M2B_TABLE_NAMES:
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name} LIMIT 1)")).scalar():
            raise RuntimeError("STOP_MENTORIA_018_DOWNGRADE_DATA_PRESENT: " + name)
    op.drop_index('ix_mt_outbox_tenant_status_next', table_name='mentoria_outbox')
    op.drop_table('mentoria_outbox')
    op.drop_index('ix_mt_audit_tenant_at', table_name='mentoria_audit_events')
    op.drop_table('mentoria_audit_events')
    op.drop_table('mentoria_access_grants')
    op.drop_index('ix_mt_enrollment_tenant_cohort_status', table_name='mentoria_enrollments')
    op.drop_table('mentoria_enrollments')
    op.drop_index('ix_mt_hold_tenant_cohort_status_exp', table_name='mentoria_seat_holds')
    op.drop_table('mentoria_seat_holds')
    op.drop_index('ix_mt_event_tenant_received', table_name='mentoria_provider_events')
    op.drop_table('mentoria_provider_events')
    op.drop_index('uq_mt_attempt_provider_payment_id', table_name='mentoria_payment_attempts')
    op.drop_table('mentoria_payment_attempts')
    op.drop_index('ix_mt_orders_tenant_financial', table_name='mentoria_orders')
    op.drop_table('mentoria_orders')
    op.drop_table('mentoria_members')
    op.drop_table('mentoria_offers')
    op.drop_table('mentoria_cohorts')
    op.drop_table('mentoria_programs')
