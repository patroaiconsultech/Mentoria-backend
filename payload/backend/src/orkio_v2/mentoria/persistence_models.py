"""M2-B persistence schema; additive, no routes or provider integration.

All business associations are tenant-scoped by composite foreign keys.
Database constraints are a second boundary; access policies remain backend-owned.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


def _id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_fk():
    return sa.ForeignKey("tenants.id", ondelete="RESTRICT")


def _status_check(column: str, states: tuple[str, ...], name: str) -> sa.CheckConstraint:
    allowed = ", ".join("'" + s + "'" for s in states)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=name)


FINANCIAL_STATES = (
    "CREATED", "AWAITING_PAYMENT", "PAID", "REVIEW_REQUIRED", "REFUNDED",
    "DISPUTED", "CHARGEBACK", "CANCELLED", "EXPIRED",
)


class MentoriaProgram(Base):
    __tablename__ = "mentoria_programs"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "id", name="uq_mt_program_identity"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_mt_program_slug"),
        _status_check("status", ("DRAFT", "PUBLISHED", "ARCHIVED"), "ck_mt_program_status"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaCohort(Base):
    __tablename__ = "mentoria_cohorts"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id", "program_id"], ["mentoria_programs.tenant_id", "mentoria_programs.id"],
                                ondelete="RESTRICT", name="fk_mt_cohort_program"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mt_cohort_identity"),
        sa.UniqueConstraint("tenant_id", "id", "program_id", name="uq_mt_cohort_program"),
        sa.CheckConstraint("capacity > 0", name="ck_mt_cohort_capacity"),
        sa.CheckConstraint("registration_closes_at > registration_opens_at", name="ck_mt_cohort_reg_window"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_mt_cohort_dates"),
        _status_check("status", ("DRAFT","OPEN","CLOSED","IN_PROGRESS","COMPLETED","CANCELLED"), "ck_mt_cohort_status"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    program_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    timezone_name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    registration_opens_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    registration_closes_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), default="DRAFT", nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaOffer(Base):
    __tablename__ = "mentoria_offers"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["tenant_id", "cohort_id", "program_id"],
            ["mentoria_cohorts.tenant_id","mentoria_cohorts.id","mentoria_cohorts.program_id"],
            ondelete="RESTRICT", name="fk_mt_offer_cohort_program",
        ),
        sa.UniqueConstraint("tenant_id","cohort_id","id","version", name="uq_mt_offer_cohort_version"),
        sa.CheckConstraint("version > 0", name="ck_mt_offer_version"),
        sa.CheckConstraint("amount_cents > 0", name="ck_mt_offer_amount"),
        sa.CheckConstraint("currency = 'BRL'", name="ck_mt_offer_currency"),
        sa.CheckConstraint("access_days > 0", name="ck_mt_offer_access"),
        _status_check("status", ("DRAFT", "PUBLISHED", "RETIRED"), "ck_mt_offer_status"),
    )
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), primary_key=True)
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    version: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    cohort_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    program_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    amount_cents: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="BRL")
    access_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    terms_version: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), default="DRAFT", nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaMember(Base):
    __tablename__ = "mentoria_members"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id","id",name="uq_mt_member_identity"),
        sa.UniqueConstraint("tenant_id","issuer","subject",name="uq_mt_member_subject"),
        _status_check("status", ("ACTIVE","SUSPENDED","REVOKED"),"ck_mt_member_status"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    issuer: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), default="ACTIVE", nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaOrder(Base):
    __tablename__ = "mentoria_orders"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","member_id"], ["mentoria_members.tenant_id","mentoria_members.id"],
                                name="fk_mt_order_member",ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id","cohort_id","offer_id","offer_version"],
                                ["mentoria_offers.tenant_id","mentoria_offers.cohort_id",
                                 "mentoria_offers.id","mentoria_offers.version"],
                                name="fk_mt_order_offer",ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id","id",name="uq_mt_order_identity"),
        sa.UniqueConstraint("tenant_id","id","cohort_id",name="uq_mt_order_cohort"),
        sa.UniqueConstraint("tenant_id","id","cohort_id","member_id",name="uq_mt_order_placement"),
        sa.UniqueConstraint("tenant_id","member_id","idempotency_key_hash",name="uq_mt_order_idempotency"),
        sa.CheckConstraint("amount_cents > 0",name="ck_mt_order_amount"),
        sa.CheckConstraint("currency = 'BRL'",name="ck_mt_order_currency"),
        _status_check("financial_state",FINANCIAL_STATES,"ck_mt_order_financial"),
        _status_check("fulfillment_state",("PENDING","PAID_UNPLACED","ENROLLED","SUSPENDED","CLOSED"),
                      "ck_mt_order_fulfillment"),
        sa.Index("ix_mt_orders_tenant_financial", "tenant_id","financial_state"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    member_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    cohort_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    offer_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    offer_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    financial_state: Mapped[str] = mapped_column(sa.String(30), default="CREATED", nullable=False)
    fulfillment_state: Mapped[str] = mapped_column(sa.String(30), default="PENDING", nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaPaymentAttempt(Base):
    __tablename__ = "mentoria_payment_attempts"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","order_id"], ["mentoria_orders.tenant_id","mentoria_orders.id"],
                                name="fk_mt_attempt_order",ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id","id",name="uq_mt_attempt_identity"),
        sa.UniqueConstraint("tenant_id","id","provider",name="uq_mt_attempt_provider"),
        sa.UniqueConstraint("provider","external_reference",name="uq_mt_attempt_external_ref"),
        sa.CheckConstraint("provider <> ''",name="ck_mt_attempt_provider_not_empty"),
        _status_check("operation_state",("NOT_STARTED","CALL_STARTED","BOUND","UNKNOWN","FAILED"),
                      "ck_mt_attempt_operation"),
        sa.Index("uq_mt_attempt_provider_payment_id", "provider","provider_payment_id",
                 unique=True, postgresql_where=sa.text("provider_payment_id IS NOT NULL")),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    order_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    provider: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    external_reference: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    operation_state: Mapped[str] = mapped_column(sa.String(20), default="NOT_STARTED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaProviderEvent(Base):
    __tablename__ = "mentoria_provider_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","payment_attempt_id","provider"],
                                ["mentoria_payment_attempts.tenant_id","mentoria_payment_attempts.id",
                                 "mentoria_payment_attempts.provider"],
                                name="fk_mt_event_attempt_provider",ondelete="RESTRICT"),
        sa.UniqueConstraint("provider","provider_event_id",name="uq_mt_event_provider_id"),
        sa.CheckConstraint("provider_event_id <> ''", name="ck_mt_event_id_not_empty"),
        sa.Index("ix_mt_event_tenant_received", "tenant_id","received_at"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    provider: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    payment_attempt_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    fact_type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class MentoriaSeatHold(Base):
    __tablename__ = "mentoria_seat_holds"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","order_id","cohort_id"],
                                ["mentoria_orders.tenant_id","mentoria_orders.id","mentoria_orders.cohort_id"],
                                name="fk_mt_hold_order_cohort",ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id","order_id",name="uq_mt_hold_order"),
        _status_check("status",("ACTIVE","CONSUMED","EXPIRED","RELEASED"),"ck_mt_hold_status"),
        sa.Index("ix_mt_hold_tenant_cohort_status_exp","tenant_id","cohort_id","status","expires_at"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    order_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    cohort_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), default="ACTIVE", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaEnrollment(Base):
    __tablename__ = "mentoria_enrollments"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","order_id","cohort_id","member_id"],
                                ["mentoria_orders.tenant_id","mentoria_orders.id",
                                 "mentoria_orders.cohort_id","mentoria_orders.member_id"],
                                name="fk_mt_enrollment_order_binding",ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id","id",name="uq_mt_enrollment_identity"),
        sa.UniqueConstraint("tenant_id","order_id",name="uq_mt_enrollment_order"),
        sa.UniqueConstraint("tenant_id","cohort_id","member_id",name="uq_mt_enrollment_member"),
        _status_check("status",("ACTIVE","SUSPENDED","CANCELLED"),"ck_mt_enrollment_status"),
        sa.Index("ix_mt_enrollment_tenant_cohort_status","tenant_id","cohort_id","status"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    order_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    cohort_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    member_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="SUSPENDED")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaAccessGrant(Base):
    __tablename__ = "mentoria_access_grants"
    __table_args__ = (
        sa.ForeignKeyConstraint(["tenant_id","enrollment_id"],
                                ["mentoria_enrollments.tenant_id","mentoria_enrollments.id"],
                                name="fk_mt_grant_enrollment",ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id","enrollment_id",name="uq_mt_grant_enrollment"),
        sa.CheckConstraint("expires_at > starts_at",name="ck_mt_grant_dates"),
        _status_check("status",("ACTIVE","SUSPENDED","REVOKED","EXPIRED"),"ck_mt_grant_status"),
        sa.CheckConstraint("status <> 'ACTIVE' OR revoked_at IS NULL",name="ck_mt_grant_active_not_revoked"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    enrollment_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="SUSPENDED")
    starts_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class MentoriaAuditEvent(Base):
    __tablename__ = "mentoria_audit_events"
    __table_args__ = (
        sa.Index("ix_mt_audit_tenant_at","tenant_id","occurred_at"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    actor_type: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    actor_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    metadata_whitelist: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)


class MentoriaOutbox(Base):
    __tablename__ = "mentoria_outbox"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id","event_key",name="uq_mt_outbox_key"),
        sa.CheckConstraint("attempt_count >= 0",name="ck_mt_outbox_attempt_count"),
        _status_check("status",("PENDING","CLAIMED","DELIVERED","FAILED"),"ck_mt_outbox_status"),
        sa.Index("ix_mt_outbox_tenant_status_next","tenant_id","status","next_attempt_at"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    event_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload_whitelist: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=_now, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


M2B_TABLES = (
    MentoriaProgram, MentoriaCohort, MentoriaOffer, MentoriaMember,
    MentoriaOrder, MentoriaPaymentAttempt, MentoriaProviderEvent,
    MentoriaSeatHold, MentoriaEnrollment, MentoriaAccessGrant,
    MentoriaAuditEvent, MentoriaOutbox,
)


class MentoriaWebhookInbox(Base):
    """Authenticated, tenant-bound receipt; NOT a financial fact or grant.

    Only sanitized payment identifiers are persisted. Raw webhook JSON and
    credentials must never be persisted or logged.
    """
    __tablename__ = "mentoria_webhook_inbox"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["tenant_id", "payment_attempt_id", "provider"],
            ["mentoria_payment_attempts.tenant_id", "mentoria_payment_attempts.id",
             "mentoria_payment_attempts.provider"],
            ondelete="RESTRICT", name="fk_mt_inbox_attempt_provider",
        ),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_mt_inbox_event"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_mt_inbox_attempts"),
        _status_check("status",
                      ("PENDING", "PROCESSING", "RETRY", "REVIEW", "PROCESSED"),
                      "ck_mt_inbox_status"),
        sa.Index("ix_mt_inbox_schedule", "status", "next_attempt_at"),
        sa.Index("ix_mt_inbox_tenant_received", "tenant_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(sa.String(64), _tenant_fk(), nullable=False)
    provider: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    payment_attempt_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payment_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=_now)
    next_attempt_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=_now)
    leased_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
