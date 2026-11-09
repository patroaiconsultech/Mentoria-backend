"""M2-B PostgreSQL-only repository for local reservation experiments.

No public endpoint, no Asaas call, no financial confirmation, no grants.
The caller owns the entire transaction: `with session.begin(): ...`.
Every producer of reservations or placements MUST lock the cohort first.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain_contracts import PriceSnapshot, order_payload_fingerprint, seat_available
from .persistence_models import (
    MentoriaAccessGrant, MentoriaAuditEvent, MentoriaCohort, MentoriaEnrollment,
    MentoriaMember, MentoriaOffer, MentoriaOrder, MentoriaOutbox,
    MentoriaProgram, MentoriaSeatHold,
)


class MentoriaPersistenceStop(RuntimeError):
    """Fail closed: no partial financial, identity, or capacity side effect."""


@dataclass(frozen=True, slots=True)
class VerifiedMentoriaIdentity:
    """Must be built by a future backend auth adapter, NEVER from request JSON."""
    tenant_id: str
    issuer: str
    subject: str


def _check_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MentoriaPersistenceStop("UTC_CLOCK_REQUIRED")
    return value.astimezone(timezone.utc)


def require_postgres_transaction(db: Session) -> None:
    """SQLite SELECT FOR UPDATE is silently ignored; NEVER use for capacity."""
    if os.environ.get("MENTORIA_M2_ENABLED", "false") != "true":
        raise MentoriaPersistenceStop("M2_FEATURE_DISABLED")
    if db.get_bind().dialect.name != "postgresql":
        raise MentoriaPersistenceStop("POSTGRESQL_ROW_LOCK_REQUIRED")
    if not db.in_transaction():
        raise MentoriaPersistenceStop("EXPLICIT_TRANSACTION_REQUIRED")


def _lock_cohort(db: Session, tenant_id: str, cohort_id: str):
    return db.scalar(
        select(MentoriaCohort).where(
            MentoriaCohort.tenant_id == tenant_id,
            MentoriaCohort.id == cohort_id,
        ).with_for_update()
    )


def reserve_checkout_order(
    db: Session, *, identity: VerifiedMentoriaIdentity,
    cohort_id: str, offer_id: str, offer_version: int,
    idempotency_key: str, request_id: str,
    now: datetime, hold_minutes: int = 30,
) -> MentoriaOrder:
    """Create order + seat hold atomically under locked cohort.

    Creates no external payment. No commit: caller commits or rolls back
    all rows. Tenant is a server-owned value provided by the auth adapter;
    never accept tenant_id from an untrusted browser payload.
    """
    require_postgres_transaction(db)
    now = _check_datetime(now)
    if not isinstance(identity, VerifiedMentoriaIdentity) or not all(
        isinstance(v, str) and v.strip()
        for v in (identity.tenant_id, identity.issuer, identity.subject, cohort_id, offer_id, request_id)
    ):
        raise MentoriaPersistenceStop("VERIFIED_IDENTITY_REQUIRED")
    if not isinstance(offer_version, int) or isinstance(offer_version, bool) or offer_version <= 0:
        raise MentoriaPersistenceStop("OFFER_VERSION_INVALID")
    if not isinstance(hold_minutes, int) or isinstance(hold_minutes, bool) or not 1 <= hold_minutes <= 1440:
        raise MentoriaPersistenceStop("HOLD_TTL_INVALID")
    if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._-]{16,128}", idempotency_key):
        raise MentoriaPersistenceStop("IDEMPOTENCY_KEY_INVALID")
    idem_hash = sha256(idempotency_key.encode("ascii")).hexdigest()

    # SERIALIZATION POINT: all writers of order+hold/enrollment in this
    # domain must take this exact tenant-scoped cohort lock first.
    cohort = _lock_cohort(db, identity.tenant_id, cohort_id)
    if cohort is None:
        raise MentoriaPersistenceStop("COHORT_UNAVAILABLE")

    member = db.scalar(select(MentoriaMember).where(
        MentoriaMember.tenant_id == identity.tenant_id,
        MentoriaMember.issuer == identity.issuer,
        MentoriaMember.subject == identity.subject,
        MentoriaMember.status == "ACTIVE",
    ))
    if member is None:
        raise MentoriaPersistenceStop("MENTORIA_IDENTITY_NOT_BOUND")
    fingerprint = order_payload_fingerprint(
        tenant_id=identity.tenant_id, buyer_subject_id=identity.issuer + ":" + identity.subject,
        offer_id=offer_id, offer_version=offer_version, cohort_id=cohort_id,
    )
    existing = db.scalar(select(MentoriaOrder).where(
        MentoriaOrder.tenant_id == identity.tenant_id,
        MentoriaOrder.member_id == member.id,
        MentoriaOrder.idempotency_key_hash == idem_hash,
    ))
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise MentoriaPersistenceStop("IDEMPOTENCY_PAYLOAD_CONFLICT")
        return existing

    if cohort.status != "OPEN":
        raise MentoriaPersistenceStop("COHORT_NOT_OPEN")
    opens_at = _check_datetime(cohort.registration_opens_at)
    closes_at = _check_datetime(cohort.registration_closes_at)
    if not opens_at <= now < closes_at:
        raise MentoriaPersistenceStop("REGISTRATION_CLOSED")

    program = db.scalar(select(MentoriaProgram).where(
        MentoriaProgram.tenant_id == identity.tenant_id,
        MentoriaProgram.id == cohort.program_id, MentoriaProgram.status == "PUBLISHED",
    ))
    offer = db.scalar(select(MentoriaOffer).where(
        MentoriaOffer.tenant_id == identity.tenant_id,
        MentoriaOffer.cohort_id == cohort.id, MentoriaOffer.program_id == cohort.program_id,
        MentoriaOffer.id == offer_id, MentoriaOffer.version == offer_version,
        MentoriaOffer.status == "PUBLISHED",
    ))
    if program is None or offer is None:
        raise MentoriaPersistenceStop("OFFER_UNAVAILABLE")
    # Snapshot only server-held price; never accept amount from the caller.
    snapshot = PriceSnapshot(
        tenant_id=identity.tenant_id, cohort_id=cohort.id, offer_id=offer.id,
        offer_version=offer.version, amount_cents=offer.amount_cents, currency=offer.currency,
    )

    # Suspended enrollment still occupies a seat: revocation of access != release.
    enrolled = db.scalar(select(func.count()).select_from(MentoriaEnrollment).where(
        MentoriaEnrollment.tenant_id == identity.tenant_id,
        MentoriaEnrollment.cohort_id == cohort.id,
        MentoriaEnrollment.status.in_(("ACTIVE","SUSPENDED")),
    )) or 0
    member_enrolled = db.scalar(select(MentoriaEnrollment.id).where(
        MentoriaEnrollment.tenant_id == identity.tenant_id,
        MentoriaEnrollment.cohort_id == cohort.id,
        MentoriaEnrollment.member_id == member.id,
        MentoriaEnrollment.status.in_(("ACTIVE","SUSPENDED")),
    ))
    if member_enrolled is not None:
        raise MentoriaPersistenceStop("MEMBER_ALREADY_ENROLLED")
    holds = db.scalar(select(func.count()).select_from(MentoriaSeatHold).where(
        MentoriaSeatHold.tenant_id == identity.tenant_id,
        MentoriaSeatHold.cohort_id == cohort.id,
        MentoriaSeatHold.status == "ACTIVE",
        MentoriaSeatHold.expires_at > now,
    )) or 0
    member_hold = db.scalar(
        select(MentoriaSeatHold.id).join(
            MentoriaOrder,
            (MentoriaOrder.tenant_id == MentoriaSeatHold.tenant_id)
            & (MentoriaOrder.id == MentoriaSeatHold.order_id),
        ).where(
            MentoriaSeatHold.tenant_id == identity.tenant_id,
            MentoriaSeatHold.cohort_id == cohort.id,
            MentoriaSeatHold.status == "ACTIVE", MentoriaSeatHold.expires_at > now,
            MentoriaOrder.member_id == member.id,
        )
    )
    if member_hold is not None:
        raise MentoriaPersistenceStop("MEMBER_ALREADY_HAS_HOLD")
    if not seat_available(capacity=cohort.capacity, active_enrollments=int(enrolled), live_holds=int(holds)):
        raise MentoriaPersistenceStop("COHORT_FULL")

    order = MentoriaOrder(
        tenant_id=identity.tenant_id, member_id=member.id, cohort_id=cohort.id,
        offer_id=offer.id, offer_version=offer.version,
        amount_cents=snapshot.amount_cents, currency=snapshot.currency,
        financial_state="CREATED", fulfillment_state="PENDING",
        idempotency_key_hash=idem_hash, request_fingerprint=fingerprint,
        created_at=now,
    )
    db.add(order)
    db.flush()
    db.add(MentoriaSeatHold(
        tenant_id=identity.tenant_id, order_id=order.id, cohort_id=cohort.id,
        expires_at=min(now + timedelta(minutes=hold_minutes), closes_at),
        status="ACTIVE", created_at=now,
    ))
    db.add(MentoriaAuditEvent(
        tenant_id=identity.tenant_id, actor_type="mentoria_member", actor_id=member.id,
        request_id=request_id, action="ORDER_RESERVED", resource_type="mentoria_order",
        resource_id=order.id, metadata_whitelist={}, occurred_at=now,
    ))
    db.add(MentoriaOutbox(
        tenant_id=identity.tenant_id, event_key="order_reserved:" + order.id,
        event_type="ORDER_RESERVED", aggregate_id=order.id, payload_whitelist={},
        status="PENDING", attempt_count=0, created_at=now,
    ))
    db.flush()
    return order
