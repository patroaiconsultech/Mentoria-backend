"""M2-C2B durable, authenticated Asaas webhook receipt (no enrollment).

Acknowledgment is allowed ONLY after a PostgreSQL commit by the HTTP caller.
The inbox contains sanitized identifiers, not webhook payload, secrets or PII.
Separate internal worker reconciles payment and changes financial state later.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .asaas_reconciliation import AuthenticatedNotification
from .persistence_models import MentoriaPaymentAttempt, MentoriaWebhookInbox
from .transactional_repository import require_postgres_transaction, _check_datetime


class WebhookIngressStopped(RuntimeError):
    """No durable acknowledgment on this failure."""


def receipt_fingerprint(notification: AuthenticatedNotification) -> str:
    if not isinstance(notification, AuthenticatedNotification):
        raise WebhookIngressStopped("AUTHENTICATED_NOTIFICATION_REQUIRED")
    canonical = json.dumps(
        [notification.event_id, notification.event_type, notification.payment_id],
        ensure_ascii=True, separators=(",", ":"),
    )
    return sha256(canonical.encode("ascii")).hexdigest()


def record_authenticated_delivery(
    db: Session, *, notification: AuthenticatedNotification, now: datetime,
) -> str:
    """Persist receipt inside caller-owned transaction. Never commit here.

    Payment ID binds to an existing provider attempt. Tenant is read from DB,
    never from the webhook body. A second webhook with same provider event ID
    must match immutable identifiers, or it is rejected as contradictory.
    """
    require_postgres_transaction(db)
    if os.environ.get("MENTORIA_M2C2B_ENABLED") != "true":
        raise WebhookIngressStopped("INGRESS_DISABLED")
    now = _check_datetime(now)
    fingerprint = receipt_fingerprint(notification)
    attempt = db.scalar(select(MentoriaPaymentAttempt).where(
        MentoriaPaymentAttempt.provider == "asaas",
        MentoriaPaymentAttempt.provider_payment_id == notification.payment_id,
        MentoriaPaymentAttempt.operation_state == "BOUND",
    ).with_for_update())
    if attempt is None:
        raise WebhookIngressStopped("UNBOUND_PAYMENT")
    existing = db.scalar(select(MentoriaWebhookInbox).where(
        MentoriaWebhookInbox.provider == "asaas",
        MentoriaWebhookInbox.provider_event_id == notification.event_id,
    ).with_for_update())
    if existing is not None:
        if (
            existing.tenant_id != attempt.tenant_id
            or existing.payment_attempt_id != attempt.id
            or existing.payment_id != notification.payment_id
            or existing.event_fingerprint != fingerprint
        ):
            raise WebhookIngressStopped("CONTRADICTORY_REPLAY")
        return "DUPLICATE_RECEIPT"

    receipt = MentoriaWebhookInbox(
        tenant_id=attempt.tenant_id, provider="asaas",
        provider_event_id=notification.event_id, payment_attempt_id=attempt.id,
        payment_id=notification.payment_id, event_type=notification.event_type,
        event_fingerprint=fingerprint, status="PENDING",
        attempt_count=0, received_at=now, next_attempt_at=now,
    )
    db.add(receipt)
    db.flush()  # global unique constraint guards cross-worker races
    return "DURABLY_RECORDED"


def ingress_enabled() -> bool:
    return os.environ.get("MENTORIA_M2_ENABLED") == "true" and (
        os.environ.get("MENTORIA_M2C2_ENABLED") == "true"
        and os.environ.get("MENTORIA_M2C2B_ENABLED") == "true"
    )
