"""M2-C2 transaction-only storage for independently verified Asaas facts.

No HTTP entrypoint and NO direct enrollment. The caller must create a
ReconciliationProof exclusively via verify_and_observe() and wrap the call in
an explicit transaction. All writes are tenant-scoped. A receipt alone is not
payment proof: fresh GET snapshot, price, ID and external reference must agree.
"""
from __future__ import annotations

from datetime import datetime
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .asaas_reconciliation import (
    FinancialProofRejected, ReconciliationProof, verified_fact,
)
from .domain_contracts import FinancialFact, FinancialState, PriceSnapshot, next_financial_state
from .fulfillment import suspend_after_reconciled_adverse_fact, _load_locked_order
from .persistence_models import (
    MentoriaAuditEvent, MentoriaOrder, MentoriaOutbox, MentoriaPaymentAttempt,
    MentoriaProviderEvent,
)
from .transactional_repository import _check_datetime, require_postgres_transaction


class ReconciliationStopped(RuntimeError):
    pass


def persist_verified_event(
    db: Session, *, proof: ReconciliationProof, request_id: str, now: datetime
) -> str:
    """Atomic, idempotent ledger update, without committing or issuing grants.

    Payment id resolves the tenant server-side; never trust a tenant in a
    notification. Cohort -> order -> attempt -> event locking sequence.
    Workers must retry serialization failures in a fresh transaction.
    """
    require_postgres_transaction(db)
    if os.environ.get("MENTORIA_M2C_ENABLED") != "true" or os.environ.get("MENTORIA_M2C2_ENABLED") != "true":
        raise ReconciliationStopped("RECONCILIATION_DISABLED")
    if not isinstance(proof, ReconciliationProof):
        raise ReconciliationStopped("PROOF_REQUIRED")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ReconciliationStopped("REQUEST_ID_REQUIRED")
    now = _check_datetime(now)
    notification, observation = proof.notification, proof.observation
    if notification.payment_id != observation.payment_id:
        raise ReconciliationStopped("PROVIDER_PAYMENT_ID_MISMATCH")

    hint = db.scalar(select(MentoriaPaymentAttempt).where(
        MentoriaPaymentAttempt.provider == "asaas",
        MentoriaPaymentAttempt.provider_payment_id == observation.payment_id,
        MentoriaPaymentAttempt.operation_state == "BOUND",
    ))
    if hint is None:
        raise ReconciliationStopped("PAYMENT_NOT_BOUND")
    tenant_id, order_id = hint.tenant_id, hint.order_id
    _, order = _load_locked_order(db, tenant_id=tenant_id, order_id=order_id)
    attempt = db.scalar(select(MentoriaPaymentAttempt).where(
        MentoriaPaymentAttempt.tenant_id == tenant_id,
        MentoriaPaymentAttempt.id == hint.id,
        MentoriaPaymentAttempt.order_id == order.id,
        MentoriaPaymentAttempt.provider == "asaas",
        MentoriaPaymentAttempt.provider_payment_id == observation.payment_id,
        MentoriaPaymentAttempt.operation_state == "BOUND",
    ).with_for_update())
    if attempt is None:
        raise ReconciliationStopped("PAYMENT_BINDING_CHANGED")
    if observation.external_reference != attempt.external_reference:
        raise ReconciliationStopped("PROVIDER_REFERENCE_MISMATCH")
    if order.currency != "BRL":
        raise ReconciliationStopped("CURRENCY_MISMATCH")

    existing = db.scalar(select(MentoriaProviderEvent).where(
        MentoriaProviderEvent.provider == "asaas",
        MentoriaProviderEvent.provider_event_id == notification.event_id,
    ).with_for_update())
    if existing is not None:
        if existing.tenant_id != tenant_id or existing.payment_attempt_id != attempt.id:
            raise ReconciliationStopped("EVENT_REPLAY_CROSS_ORDER")
        if existing.processed_at is None:
            raise ReconciliationStopped("EVENT_RECONCILIATION_PENDING")
        return "ALREADY_PROCESSED"

    # Remote mismatch is a review fact, not a financial positive.
    fact_code = (
        verified_fact(proof)
        if observation.amount_cents == order.amount_cents else "UNKNOWN"
    )
    snapshot = PriceSnapshot(
        tenant_id=tenant_id, offer_id=order.offer_id, cohort_id=order.cohort_id,
        offer_version=order.offer_version, amount_cents=order.amount_cents,
        currency="BRL",
    )
    try:
        next_state = next_financial_state(
            FinancialState(order.financial_state),
            FinancialFact(fact_code),
            snapshot=snapshot,
            observed_amount_cents=observation.amount_cents,
            observed_currency="BRL",
        )
    except (ValueError, FinancialProofRejected) as exc:
        raise ReconciliationStopped("FINANCIAL_STATE_INVALID") from exc

    order.financial_state = next_state.value
    db.add(MentoriaProviderEvent(
        tenant_id=tenant_id, provider="asaas",
        provider_event_id=notification.event_id, payment_attempt_id=attempt.id,
        fact_type=fact_code, received_at=now, processed_at=now,
    ))
    db.flush()

    # Financial adverse state blocks access immediately through backend access
    # policy, and existing enrollment/grant must also be suspended atomically.
    if next_state not in (FinancialState.PAID, FinancialState.CREATED,
                          FinancialState.AWAITING_PAYMENT):
        suspend_after_reconciled_adverse_fact(
            db, tenant_id=tenant_id, order_id=order.id, request_id=request_id,
            now=now,
        )

    db.add(MentoriaAuditEvent(
        tenant_id=tenant_id, actor_type="provider_reconciler",
        actor_id="asaas", request_id=request_id,
        action="MENTORIA_PAYMENT_RECONCILED",
        resource_type="mentoria_order", resource_id=order.id,
        metadata_whitelist={"financial_state":next_state.value},
        occurred_at=now,
    ))
    db.add(MentoriaOutbox(
        tenant_id=tenant_id, event_key=f"financial:{notification.event_id}",
        event_type="MENTORIA_PAYMENT_RECONCILED",
        aggregate_id=order.id, payload_whitelist={"financial_state":next_state.value},
        status="PENDING", attempt_count=0, created_at=now,
    ))
    db.flush()
    return next_state.value
