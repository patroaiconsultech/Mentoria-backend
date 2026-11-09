"""M2-C1: internal PostgreSQL fulfillment after trusted financial reconciliation.

SOURCE_PROPOSAL_ONLY. No HTTP route or provider adapter is installed here.
ONLY the future authenticated backend reconciliation worker may mark an
event processed and an order PAID. Neither a browser nor a raw webhook
may invoke this module as proof of payment.

All writers MUST lock the tenant-scoped cohort first, then order, then
associated rows; caller owns commit/rollback. No external I/O in a lock.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .persistence_models import (
    MentoriaAccessGrant, MentoriaAuditEvent, MentoriaCohort, MentoriaEnrollment,
    MentoriaMember, MentoriaOffer, MentoriaOrder, MentoriaOutbox,
    MentoriaPaymentAttempt, MentoriaProviderEvent, MentoriaSeatHold,
)
from .transactional_repository import (
    MentoriaPersistenceStop, _check_datetime, _lock_cohort,
    require_postgres_transaction,
)


class MentoriaFulfillmentStop(MentoriaPersistenceStop):
    """No unsafe fallback to granting or silently dropping a paid order."""


def _require_enabled(db: Session) -> None:
    try:
        require_postgres_transaction(db)
    except MentoriaPersistenceStop as exc:
        raise MentoriaFulfillmentStop(str(exc)) from exc
    if os.environ.get("MENTORIA_M2C_ENABLED", "false").lower() != "true":
        raise MentoriaFulfillmentStop("M2C_FEATURE_DISABLED")


def _required_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 128) or not value.strip():
        raise MentoriaFulfillmentStop(f"{name}_REQUIRED")
    return value


def _audit(db: Session, *, tenant_id: str, order_id: str, request_id: str,
           now: datetime, action: str) -> None:
    db.add(MentoriaAuditEvent(
        tenant_id=tenant_id, actor_type="mentoria_reconciler",
        actor_id="internal", request_id=request_id, action=action,
        resource_type="mentoria_order", resource_id=order_id,
        metadata_whitelist={}, occurred_at=now,
    ))
    db.add(MentoriaOutbox(
        tenant_id=tenant_id, event_key=f"{action.lower()}:{order_id}",
        event_type=action, aggregate_id=order_id,
        payload_whitelist={}, status="PENDING", attempt_count=0, created_at=now,
    ))


def _load_locked_order(db: Session, *, tenant_id: str, order_id: str):
    """Read cohort identifier, take the canonical lock, then re-read order.

    Every writer must follow this lock order. The initial read is only a hint;
    tenant and cohort bindings are validated a second time under the lock.
    """
    provisional = db.scalar(select(MentoriaOrder).where(
        MentoriaOrder.tenant_id == tenant_id, MentoriaOrder.id == order_id,
    ))
    if provisional is None:
        raise MentoriaFulfillmentStop("ORDER_UNAVAILABLE")
    cohort_id = provisional.cohort_id
    cohort = _lock_cohort(db, tenant_id, cohort_id)
    if cohort is None:
        raise MentoriaFulfillmentStop("COHORT_UNAVAILABLE")
    order = db.scalar(select(MentoriaOrder).where(
        MentoriaOrder.tenant_id == tenant_id,
        MentoriaOrder.id == order_id,
        MentoriaOrder.cohort_id == cohort.id,
    ).with_for_update())
    if order is None:
        raise MentoriaFulfillmentStop("ORDER_CHANGED_DURING_LOCK")
    return cohort, order


def _has_confirmed_reconciliation(db: Session, order: MentoriaOrder) -> bool:
    """Only previously *processed* canonical provider events count.

    A raw webhook, a payment attempt or the order's PAID field alone is
    never sufficient. The provider adapter must independently validate the
    provider's account/payment, event authenticity and amount BEFORE it
    commits these canonical records. That adapter is NOT in this patch.
    """
    event_id = db.scalar(
        select(MentoriaProviderEvent.id).join(
            MentoriaPaymentAttempt,
            (MentoriaPaymentAttempt.tenant_id == MentoriaProviderEvent.tenant_id)
            & (MentoriaPaymentAttempt.id == MentoriaProviderEvent.payment_attempt_id)
            & (MentoriaPaymentAttempt.provider == MentoriaProviderEvent.provider),
        ).where(
            MentoriaProviderEvent.tenant_id == order.tenant_id,
            MentoriaPaymentAttempt.order_id == order.id,
            MentoriaPaymentAttempt.operation_state == "BOUND",
            MentoriaPaymentAttempt.provider_payment_id.is_not(None),
            MentoriaPaymentAttempt.provider_payment_id != "",
            MentoriaProviderEvent.fact_type == "CONFIRMED",
            MentoriaProviderEvent.processed_at.is_not(None),
        ).limit(1)
    )
    return event_id is not None


def _make_paid_unplaced(db: Session, *, order: MentoriaOrder,
                        hold: MentoriaSeatHold | None, now: datetime,
                        request_id: str) -> None:
    if order.fulfillment_state != "PAID_UNPLACED":
        order.fulfillment_state = "PAID_UNPLACED"
        if hold is not None and hold.status == "ACTIVE" and _check_datetime(hold.expires_at) <= now:
            hold.status = "EXPIRED"
        _audit(db, tenant_id=order.tenant_id, order_id=order.id,
               request_id=request_id, now=now, action="PAID_UNPLACED")
    db.flush()


def place_reconciled_paid_order(
    db: Session, *, tenant_id: str, order_id: str, request_id: str, now: datetime,
) -> MentoriaEnrollment | None:
    """Internal, transaction-owned placement; None means PAID_UNPLACED.

    Requires a PAID order *and* a previously processed confirmation event
    linked via a bound provider attempt, ACTIVE verified member, valid hold,
    capacity under the locked cohort, and a valid offer snapshot.

    Never infer payment from frontend/webhook payload. No auto-retry of a
    PAID_UNPLACED order, and no grant resurrection after suspension/revocation.
    """
    _require_enabled(db)
    tenant_id = _required_id(tenant_id, "TENANT_ID")
    order_id = _required_id(order_id, "ORDER_ID")
    request_id = _required_id(request_id, "REQUEST_ID")
    now = _check_datetime(now)
    cohort, order = _load_locked_order(db, tenant_id=tenant_id, order_id=order_id)

    # Check payment evidence before idempotent re-entry as well; a later
    # adverse state must never appear to be a successfully active enrollment.
    if order.financial_state != "PAID" or not _has_confirmed_reconciliation(db, order):
        raise MentoriaFulfillmentStop("PAYMENT_NOT_RECONCILED")
    enrollment = db.scalar(select(MentoriaEnrollment).where(
        MentoriaEnrollment.tenant_id == tenant_id,
        MentoriaEnrollment.order_id == order.id,
    ).with_for_update())
    if order.fulfillment_state == "ENROLLED":
        member_active = db.scalar(select(MentoriaMember.id).where(
            MentoriaMember.tenant_id == tenant_id,
            MentoriaMember.id == order.member_id,
            MentoriaMember.status == "ACTIVE",
            MentoriaMember.email_verified_at.is_not(None),
        )) is not None
        grant = db.scalar(select(MentoriaAccessGrant).where(
            MentoriaAccessGrant.tenant_id == tenant_id,
            MentoriaAccessGrant.enrollment_id == enrollment.id if enrollment else False,
        ))
        if (
            member_active and enrollment is not None and enrollment.status == "ACTIVE"
            and grant is not None and grant.status == "ACTIVE"
            and grant.revoked_at is None
            and _check_datetime(grant.starts_at) <= now < _check_datetime(grant.expires_at)
        ):
            return enrollment
        raise MentoriaFulfillmentStop("ENROLLMENT_INCONSISTENT")
    if enrollment is not None:
        raise MentoriaFulfillmentStop("ENROLLMENT_ALREADY_EXISTS")
    if order.fulfillment_state == "PAID_UNPLACED":
        return None
    if order.fulfillment_state != "PENDING":
        raise MentoriaFulfillmentStop("ORDER_NOT_PLACEABLE")
    member = db.scalar(select(MentoriaMember).where(
        MentoriaMember.tenant_id == tenant_id,
        MentoriaMember.id == order.member_id,
        MentoriaMember.status == "ACTIVE",
        MentoriaMember.email_verified_at.is_not(None),
    ))
    if member is None:
        raise MentoriaFulfillmentStop("VERIFIED_MEMBER_REQUIRED")
    offer = db.scalar(select(MentoriaOffer).where(
        MentoriaOffer.tenant_id == tenant_id, MentoriaOffer.id == order.offer_id,
        MentoriaOffer.version == order.offer_version,
        MentoriaOffer.cohort_id == cohort.id,
        MentoriaOffer.program_id == cohort.program_id,
    ))
    if offer is None or (offer.amount_cents, offer.currency) != (order.amount_cents, order.currency):
        raise MentoriaFulfillmentStop("ORDER_PRICE_SNAPSHOT_MISMATCH")
    if not isinstance(offer.access_days, int) or offer.access_days <= 0:
        raise MentoriaFulfillmentStop("ACCESS_PERIOD_INVALID")

    hold = db.scalar(select(MentoriaSeatHold).where(
        MentoriaSeatHold.tenant_id == tenant_id,
        MentoriaSeatHold.order_id == order.id,
        MentoriaSeatHold.cohort_id == cohort.id,
    ).with_for_update())

    # A late payment is a financial obligation, not authorization to steal a seat.
    if (
        hold is None or hold.status != "ACTIVE"
        or _check_datetime(hold.expires_at) <= now
        or cohort.status == "CANCELLED"
        or _check_datetime(cohort.ends_at) <= now
    ):
        _make_paid_unplaced(db, order=order, hold=hold, now=now,
                            request_id=request_id)
        return None

    enrolled = int(db.scalar(select(func.count()).select_from(MentoriaEnrollment).where(
        MentoriaEnrollment.tenant_id == tenant_id,
        MentoriaEnrollment.cohort_id == cohort.id,
        MentoriaEnrollment.status.in_(("ACTIVE", "SUSPENDED")),
    )) or 0)
    active_holds = int(db.scalar(select(func.count()).select_from(MentoriaSeatHold).where(
        MentoriaSeatHold.tenant_id == tenant_id,
        MentoriaSeatHold.cohort_id == cohort.id,
        MentoriaSeatHold.status == "ACTIVE",
        MentoriaSeatHold.expires_at > now,
    )) or 0)
    # Current hold is already counted. Another writer must lock this cohort.
    if enrolled + active_holds > cohort.capacity:
        raise MentoriaFulfillmentStop("CAPACITY_INVARIANT_BROKEN")

    enrollment = MentoriaEnrollment(
        tenant_id=tenant_id, order_id=order.id, cohort_id=cohort.id,
        member_id=member.id, status="ACTIVE", created_at=now,
    )
    db.add(enrollment)
    db.flush()
    db.add(MentoriaAccessGrant(
        tenant_id=tenant_id, enrollment_id=enrollment.id,
        status="ACTIVE", starts_at=now,
        expires_at=now + timedelta(days=offer.access_days),
    ))
    hold.status = "CONSUMED"
    order.fulfillment_state = "ENROLLED"
    _audit(db, tenant_id=tenant_id, order_id=order.id, request_id=request_id,
           now=now, action="MENTORIA_PLACED")
    db.flush()
    return enrollment


def suspend_after_reconciled_adverse_fact(
    db: Session, *, tenant_id: str, order_id: str, request_id: str, now: datetime,
) -> bool:
    """Revoke/suspend access only after *upstream* authenticated reconciliation.

    The upstream worker MUST persist the adverse event and financial_state
    in the same DB transaction before invoking this. This is NOT a webhook.
    Returns False if no enrollment exists; preserves financial history.
    """
    _require_enabled(db)
    tenant_id = _required_id(tenant_id, "TENANT_ID")
    order_id = _required_id(order_id, "ORDER_ID")
    request_id = _required_id(request_id, "REQUEST_ID")
    now = _check_datetime(now)
    _, order = _load_locked_order(db, tenant_id=tenant_id, order_id=order_id)
    if order.financial_state in ("PAID", "CREATED", "AWAITING_PAYMENT"):
        raise MentoriaFulfillmentStop("NO_RECONCILED_ADVERSE_STATE")
    if order.financial_state not in (
        "REVIEW_REQUIRED", "REFUNDED", "DISPUTED", "CHARGEBACK", "CANCELLED", "EXPIRED",
    ):
        raise MentoriaFulfillmentStop("UNKNOWN_FINANCIAL_STATE")
    # A provisional state change alone is not sufficient evidence.
    has_adverse_event = db.scalar(
        select(MentoriaProviderEvent.id).join(
            MentoriaPaymentAttempt,
            (MentoriaPaymentAttempt.tenant_id == MentoriaProviderEvent.tenant_id)
            & (MentoriaPaymentAttempt.id == MentoriaProviderEvent.payment_attempt_id)
            & (MentoriaPaymentAttempt.provider == MentoriaProviderEvent.provider),
        ).where(
            MentoriaProviderEvent.tenant_id == tenant_id,
            MentoriaPaymentAttempt.order_id == order.id,
            MentoriaProviderEvent.fact_type.in_(
                ("REFUNDED", "PARTIAL_REFUND", "DISPUTE_OPENED", "CHARGEBACK",
                 "DISPUTE_RESOLVED", "CANCELLED", "EXPIRED", "UNKNOWN")
            ),
            MentoriaProviderEvent.processed_at.is_not(None),
        ).limit(1)
    )
    if has_adverse_event is None:
        raise MentoriaFulfillmentStop("ADVERSE_EVENT_NOT_RECONCILED")

    enrollment = db.scalar(select(MentoriaEnrollment).where(
        MentoriaEnrollment.tenant_id == tenant_id,
        MentoriaEnrollment.order_id == order.id,
    ).with_for_update())
    if enrollment is None:
        return False
    grant = db.scalar(select(MentoriaAccessGrant).where(
        MentoriaAccessGrant.tenant_id == tenant_id,
        MentoriaAccessGrant.enrollment_id == enrollment.id,
    ).with_for_update())
    if grant is None:
        raise MentoriaFulfillmentStop("GRANT_MISSING")
    terminal = order.financial_state in ("REFUNDED", "CHARGEBACK")
    desired = "REVOKED" if terminal else "SUSPENDED"
    if grant.status == desired and order.fulfillment_state == "SUSPENDED":
        return True
    if grant.status == "REVOKED" and not terminal:
        # Never undo a terminal revocation based on a later softer fact.
        desired = "REVOKED"
    grant.status = desired
    if desired == "REVOKED":
        grant.revoked_at = now if grant.revoked_at is None else grant.revoked_at
    enrollment.status = "SUSPENDED"
    order.fulfillment_state = "SUSPENDED"
    _audit(db, tenant_id=tenant_id, order_id=order.id, request_id=request_id,
           now=now, action="MENTORIA_ACCESS_SUSPENDED")
    db.flush()
    return True
