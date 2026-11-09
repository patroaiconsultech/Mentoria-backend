"""Internal worker for durable inbox (no HTTP or automatic enrollment).

Claim -> commit -> read-only Asaas GET -> atomic financial ledger + inbox commit.
Leases allow recovery after process crash; PostgreSQL row locks serialize claims.
A financial error always leaves receipt RETRY or REVIEW, never PROCESSED.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .asaas_reconciliation import (
    AuthenticatedNotification, AsaasReadOnlyPayments, FinancialProofRejected,
    ReconciliationProof,
)
from .financial_ledger import ReconciliationStopped, persist_verified_event
from .m2c2b_ingress import ingress_enabled
from .persistence_models import MentoriaWebhookInbox, MentoriaPaymentAttempt
from .transactional_repository import _check_datetime, require_postgres_transaction

MAX_ATTEMPTS = 12
LEASE_SECONDS = 180
RETRYABLE_PROVIDER_CODES = frozenset({
    "ASAAS_LOOKUP_FAILED", "ASAAS_LOOKUP_NOT_CONFIRMED",
})


class WorkerStopped(RuntimeError):
    pass


def _select_receipt(db: Session, receipt_id: str) -> MentoriaWebhookInbox | None:
    return db.scalar(select(MentoriaWebhookInbox).where(
        MentoriaWebhookInbox.id == receipt_id,
    ).with_for_update(skip_locked=True))


def _claim(db: Session, *, receipt_id: str, now: datetime) -> tuple | None:
    require_postgres_transaction(db)
    r = _select_receipt(db, receipt_id)
    if r is None or r.status in {"REVIEW", "PROCESSED"}:
        return None
    due = r.status in {"PENDING", "RETRY"} and r.next_attempt_at <= now
    abandoned = (
        r.status == "PROCESSING" and r.leased_at is not None
        and r.leased_at <= now - timedelta(seconds=LEASE_SECONDS)
    )
    if not (due or abandoned):
        return None
    if r.attempt_count >= MAX_ATTEMPTS:
        r.status = "REVIEW"
        r.last_error_code = "MAX_ATTEMPTS"
        db.flush()
        return None
    r.status = "PROCESSING"
    r.attempt_count += 1
    r.leased_at = now
    r.last_error_code = None
    db.flush()
    return (r.tenant_id, r.provider_event_id, r.event_type,
            r.payment_id, r.payment_attempt_id, r.attempt_count)


def _fail(db: Session, *, receipt_id: str, attempt_number: int, now: datetime, code: str, retry: bool) -> None:
    require_postgres_transaction(db)
    r = _select_receipt(db, receipt_id)
    if r is None or r.status != "PROCESSING" or r.attempt_count != attempt_number:
        raise WorkerStopped("LEASE_CHANGED")
    # No free-form external text is persisted; only short fixed error codes.
    r.status = "RETRY" if retry and r.attempt_count < MAX_ATTEMPTS else "REVIEW"
    r.last_error_code = code
    r.leased_at = None
    r.next_attempt_at = now + timedelta(seconds=min(3600, 15 * (2 ** min(r.attempt_count, 8))))
    db.flush()


def process_one(
    *, receipt_id: str, session_factory: Callable[[], Session],
    provider: AsaasReadOnlyPayments, now: datetime, request_id: str,
) -> str:
    """Claim/reconcile one pre-authenticated receipt; caller owns scheduling.

    Must NOT run from the webhook HTTP request. No checkout, refund, grant or
    enrollment mutation is performed except existing adverse grant suspension.
    """
    now = _check_datetime(now)
    if not ingress_enabled():
        raise WorkerStopped("M2C2B_DISABLED")
    if not isinstance(receipt_id, str) or not 1 <= len(receipt_id) <= 64:
        raise WorkerStopped("RECEIPT_ID_INVALID")
    with session_factory() as db:
        with db.begin():
            claim = _claim(db, receipt_id=receipt_id, now=now)
    if claim is None:
        return "NOT_DUE"
    tenant_id, event_id, event_type, payment_id, attempt_id, attempt_number = claim

    try:
        observation = provider.get_payment(payment_id)
        notification = AuthenticatedNotification(event_id, event_type, payment_id)
        proof = ReconciliationProof(notification, observation)
    except FinancialProofRejected as exc:
        error_code = str(exc)
        with session_factory() as db:
            with db.begin():
                _fail(db, receipt_id=receipt_id, attempt_number=attempt_number, now=now, code=(
                    error_code if error_code in RETRYABLE_PROVIDER_CODES
                    else "PROVIDER_PROOF_INVALID"
                ), retry=error_code in RETRYABLE_PROVIDER_CODES)
        return "RETRY_OR_REVIEW"

    try:
        with session_factory() as db:
            with db.begin():
                require_postgres_transaction(db)
                inbox = _select_receipt(db, receipt_id)
                if (
                    inbox is None or inbox.status != "PROCESSING"
                    or inbox.tenant_id != tenant_id or inbox.payment_attempt_id != attempt_id
                    or inbox.attempt_count != attempt_number
                    or inbox.provider_event_id != event_id
                ):
                    raise WorkerStopped("LEASE_CHANGED")
                binding = db.scalar(select(MentoriaPaymentAttempt).where(
                    MentoriaPaymentAttempt.id == attempt_id,
                    MentoriaPaymentAttempt.tenant_id == tenant_id,
                    MentoriaPaymentAttempt.provider == "asaas",
                    MentoriaPaymentAttempt.provider_payment_id == payment_id,
                    MentoriaPaymentAttempt.operation_state == "BOUND",
                ).with_for_update())
                if binding is None:
                    raise ReconciliationStopped("PAYMENT_BINDING_CHANGED")
                result = persist_verified_event(db, proof=proof, request_id=request_id, now=now)
                inbox.status = "PROCESSED"
                inbox.processed_at = now
                inbox.leased_at = None
                db.flush()
        return result
    except ReconciliationStopped:
        # Real financial mismatch is quarantined, never treated as paid.
        with session_factory() as db:
            with db.begin():
                _fail(db, receipt_id=receipt_id, attempt_number=attempt_number, now=now,
                      code="FINANCIAL_RECONCILIATION_REVIEW", retry=False)
        return "REVIEW"
    # Unexpected DB failures propagate; recovery occurs after lease expiry.
