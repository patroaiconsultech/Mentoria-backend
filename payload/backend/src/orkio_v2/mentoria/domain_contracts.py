"""M2-A: contratos puros de domínio (sem DB, HTTP, billing ou grants).

SOURCE_PROPOSAL_ONLY. Este módulo NÃO verifica autenticidade de webhook,
NÃO cria pedidos, NÃO processa cobranças e NÃO concede acesso. As funções
somente recebem fatos já autenticados/reconciliados por infraestrutura futura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json


class ContractViolation(ValueError):
    """Invariante de negócio violada: negar a operação, nunca degradar."""


class FinancialState(str, Enum):
    CREATED = "CREATED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAID = "PAID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"
    CHARGEBACK = "CHARGEBACK"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class FinancialFact(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REFUNDED = "REFUNDED"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    CHARGEBACK = "CHARGEBACK"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class EnrollmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class GrantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{field}_REQUIRED")
    return value


def _positive_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractViolation(f"{field}_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """Imutável: gerado do catálogo no servidor, nunca da UI."""
    tenant_id: str
    offer_id: str
    cohort_id: str
    offer_version: int
    amount_cents: int
    currency: str = "BRL"

    def __post_init__(self) -> None:
        for key in ("tenant_id", "offer_id", "cohort_id"):
            _required(getattr(self, key), key)
        _positive_int(self.offer_version, "offer_version")
        _positive_int(self.amount_cents, "amount_cents")
        if self.currency != "BRL":
            raise ContractViolation("CURRENCY_UNSUPPORTED")


def order_payload_fingerprint(
    *, tenant_id: str, buyer_subject_id: str, offer_id: str,
    offer_version: int, cohort_id: str
) -> str:
    """Fingerprint da intenção comercial, sem preço/tenant vindos do browser.

    NÃO substitui Idempotency-Key, banco UNIQUE nem lock transacional.
    """
    payload = {
        "tenant_id": _required(tenant_id, "tenant_id"),
        "buyer_subject_id": _required(buyer_subject_id, "buyer_subject_id"),
        "offer_id": _required(offer_id, "offer_id"),
        "offer_version": _positive_int(offer_version, "offer_version"),
        "cohort_id": _required(cohort_id, "cohort_id"),
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def next_financial_state(
    current: FinancialState,
    fact: FinancialFact,
    *,
    snapshot: PriceSnapshot,
    observed_amount_cents: int | None = None,
    observed_currency: str | None = None,
) -> FinancialState:
    """Redutor CONSERVADOR de fatos financeiros previamente verificados.

    O adapter futuro valida o header Asaas, event_id, payment_id, valor
    contratado, conta/provider, ordenação e reconciliação antes desta chamada.
    Fatos desconhecidos e estornos parciais nunca concedem acesso.
    """
    if not isinstance(current, FinancialState) or not isinstance(fact, FinancialFact):
        raise ContractViolation("FINANCIAL_FACT_INVALID")

    # Estados adversos confirmados não podem ser ressuscitados por evento atrasado.
    if current in (FinancialState.REFUNDED, FinancialState.CHARGEBACK):
        return current

    if fact == FinancialFact.CHARGEBACK:
        return FinancialState.CHARGEBACK
    if fact == FinancialFact.REFUNDED:
        return FinancialState.REFUNDED
    if fact == FinancialFact.DISPUTE_OPENED:
        return FinancialState.DISPUTED
    if fact in (FinancialFact.PARTIAL_REFUND, FinancialFact.DISPUTE_RESOLVED, FinancialFact.UNKNOWN):
        return FinancialState.REVIEW_REQUIRED
    if fact == FinancialFact.CONFIRMED:
        if (
            isinstance(observed_amount_cents, bool)
            or not isinstance(observed_amount_cents, int)
            or observed_amount_cents != snapshot.amount_cents
            or observed_currency != snapshot.currency
        ):
            return FinancialState.REVIEW_REQUIRED
        if current in (FinancialState.CREATED, FinancialState.AWAITING_PAYMENT, FinancialState.PAID):
            return FinancialState.PAID
        # Confirmação tardia após contestação, expiração ou cancelamento:
        # bloquear até conciliação/manual decision, nunca conceder grant.
        return FinancialState.REVIEW_REQUIRED
    if fact == FinancialFact.PENDING:
        return (FinancialState.AWAITING_PAYMENT
                if current == FinancialState.CREATED else current)
    if fact in (FinancialFact.CANCELLED, FinancialFact.EXPIRED):
        if current in (FinancialState.CREATED, FinancialState.AWAITING_PAYMENT):
            return (FinancialState.CANCELLED if fact == FinancialFact.CANCELLED
                    else FinancialState.EXPIRED)
        if current in (FinancialState.CANCELLED, FinancialState.EXPIRED):
            return current
        return FinancialState.REVIEW_REQUIRED
    raise ContractViolation("FINANCIAL_FACT_INVALID")


def seat_available(*, capacity: int, active_enrollments: int, live_holds: int) -> bool:
    """Somente predicado. SEM lock PostgreSQL, NÃO reserva vagas."""
    _positive_int(capacity, "capacity")
    for value, name in ((active_enrollments, "active_enrollments"), (live_holds, "live_holds")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractViolation(f"{name}_INVALID")
    return active_enrollments + live_holds < capacity


@dataclass(frozen=True, slots=True)
class AccessSnapshot:
    """Apenas dados que o futuro repositório autorizado deverá retornar."""
    tenant_id: str
    buyer_subject_id: str
    cohort_id: str
    financial_state: FinancialState
    enrollment_status: EnrollmentStatus
    grant_status: GrantStatus
    grant_starts_at: datetime
    grant_expires_at: datetime
    revoked_at: datetime | None = None


def allows_mentoria_access(
    *, principal_subject_id: str, owner_tenant_id: str,
    requested_cohort_id: str, snapshot: AccessSnapshot | None,
    now: datetime,
) -> bool:
    """Predicado fail-closed. NÃO é middleware nem endpoint de autorização.

    Sem identidade autenticada, snapshot persistido de mesmo owner/subject/cohort,
    pagamento PAID, enrollment/grant ACTIVE e validade UTC: acesso negado.
    """
    if snapshot is None or not all(
        isinstance(value, str) and value.strip()
        for value in (principal_subject_id, owner_tenant_id, requested_cohort_id)
    ):
        return False
    if (
        snapshot.tenant_id != owner_tenant_id
        or snapshot.buyer_subject_id != principal_subject_id
        or snapshot.cohort_id != requested_cohort_id
        or snapshot.financial_state != FinancialState.PAID
        or snapshot.enrollment_status != EnrollmentStatus.ACTIVE
        or snapshot.grant_status != GrantStatus.ACTIVE
        or snapshot.revoked_at is not None
    ):
        return False
    times = (now, snapshot.grant_starts_at, snapshot.grant_expires_at)
    if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in times):
        return False
    return snapshot.grant_starts_at.astimezone(timezone.utc) <= now.astimezone(timezone.utc) < snapshot.grant_expires_at.astimezone(timezone.utc)
