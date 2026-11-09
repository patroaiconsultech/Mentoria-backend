"""M2-C2: Asaas webhook authentication + independent payment observation.

SOURCE_PROPOSAL_ONLY. No public route. No automatic checkout or enrollment.
Never accept financial truth from the browser or from a webhook body.
The only authoritative payment snapshot comes from a read-only, server-side
Asaas GET on a fixed HTTPS origin using a server-side API key.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hmac import compare_digest
import re
from typing import Any, Mapping

import httpx

_ALLOWED_BASES = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "production": "https://api.asaas.com/v3",
}
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_EVENT_ID = re.compile(r"^[A-Za-z0-9_.:&-]{1,128}$")
_EVENTS = frozenset({
    "PAYMENT_CONFIRMED", "PAYMENT_RECEIVED",
    "PAYMENT_REFUNDED", "PAYMENT_PARTIALLY_REFUNDED",
    "PAYMENT_REFUND_IN_PROGRESS", "PAYMENT_CHARGEBACK_REQUESTED",
    "PAYMENT_CHARGEBACK_DISPUTE", "PAYMENT_AWAITING_CHARGEBACK_REVERSAL",
    "PAYMENT_UPDATED", "PAYMENT_DELETED", "PAYMENT_RECEIVED_IN_CASH_UNDONE",
})


class FinancialProofRejected(ValueError):
    """Proof unavailable or ambiguous; caller must fail closed, never grant."""


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FinancialProofRejected(f"{name}_INVALID")
    return value


def _event_identifier(value: object) -> str:
    if not isinstance(value, str) or not _EVENT_ID.fullmatch(value):
        raise FinancialProofRejected("EVENT_ID_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class AuthenticatedNotification:
    event_id: str
    event_type: str
    payment_id: str


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """Made from a successful authenticated GET; NOT from incoming JSON."""
    payment_id: str
    external_reference: str
    status: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class ReconciliationProof:
    notification: AuthenticatedNotification
    observation: ProviderObservation


def authenticate_notification(
    *, header_token: str | None, configured_token: str, payload: Any
) -> AuthenticatedNotification:
    """Asaas sends authToken in `asaas-access-token`, not a Bearer token."""
    if (
        not isinstance(configured_token, str)
        or not 32 <= len(configured_token) <= 255
        or any(c.isspace() for c in configured_token)
    ):
        raise FinancialProofRejected("WEBHOOK_NOT_CONFIGURED")
    if not isinstance(header_token, str) or not compare_digest(
        header_token.encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise FinancialProofRejected("WEBHOOK_UNAUTHENTICATED")
    if not isinstance(payload, dict) or not isinstance(payload.get("payment"), dict):
        raise FinancialProofRejected("WEBHOOK_PAYLOAD_INVALID")
    event_type = payload.get("event")
    if event_type not in _EVENTS:
        raise FinancialProofRejected("WEBHOOK_EVENT_UNSUPPORTED")
    return AuthenticatedNotification(
        event_id=_event_identifier(payload.get("id")),
        event_type=event_type,
        payment_id=_identifier(payload["payment"].get("id"), "PAYMENT_ID"),
    )


def _to_cents(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise FinancialProofRejected("PROVIDER_AMOUNT_INVALID")
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise FinancialProofRejected("PROVIDER_AMOUNT_INVALID") from None
    if not numeric.is_finite() or numeric <= 0:
        raise FinancialProofRejected("PROVIDER_AMOUNT_INVALID")
    cents = numeric * 100
    if cents != cents.to_integral_value() or cents > 10**12:
        raise FinancialProofRejected("PROVIDER_AMOUNT_INVALID")
    return int(cents)


class AsaasReadOnlyPayments:
    """No dynamic base URL, redirect, mutation, proxy or credential logging."""

    def __init__(
        self, *, api_key: str, environment: str,
        transport: httpx.BaseTransport | None = None, timeout: float = 8.0
    ):
        if environment not in _ALLOWED_BASES or not isinstance(api_key, str) or not api_key.strip():
            raise FinancialProofRejected("ASAAS_CLIENT_NOT_CONFIGURED")
        if not 0 < timeout <= 15:
            raise FinancialProofRejected("ASAAS_TIMEOUT_INVALID")
        self._base = _ALLOWED_BASES[environment]
        self._key = api_key
        self._transport = transport
        self._timeout = timeout

    def get_payment(self, payment_id: str) -> ProviderObservation:
        payment_id = _identifier(payment_id, "PAYMENT_ID")
        try:
            with httpx.Client(
                transport=self._transport, timeout=self._timeout,
                trust_env=False, follow_redirects=False,
            ) as client:
                response = client.get(
                    f"{self._base}/payments/{payment_id}",
                    headers={"access_token": self._key, "Accept": "application/json"},
                )
            if response.status_code != 200:
                raise FinancialProofRejected("ASAAS_LOOKUP_NOT_CONFIRMED")
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FinancialProofRejected("ASAAS_LOOKUP_FAILED") from exc
        if not isinstance(body, dict) or body.get("id") != payment_id:
            raise FinancialProofRejected("ASAAS_PAYMENT_MISMATCH")
        reference = body.get("externalReference")
        if not isinstance(reference, str) or not 1 <= len(reference) <= 128:
            raise FinancialProofRejected("ASAAS_REFERENCE_INVALID")
        status = body.get("status")
        if not isinstance(status, str) or len(status) > 60:
            raise FinancialProofRejected("ASAAS_STATUS_INVALID")
        return ProviderObservation(
            payment_id=payment_id,
            external_reference=reference,
            status=status,
            amount_cents=_to_cents(body.get("value")),
        )


def verify_and_observe(
    *, header_token: str | None, configured_token: str,
    payload: Mapping[str, Any], provider: AsaasReadOnlyPayments,
) -> ReconciliationProof:
    """Do network I/O BEFORE database row locks. No caller-supplied tenant."""
    notification = authenticate_notification(
        header_token=header_token, configured_token=configured_token,
        payload=payload,
    )
    observation = provider.get_payment(notification.payment_id)
    return ReconciliationProof(notification=notification, observation=observation)


def verified_fact(proof: ReconciliationProof) -> str:
    """Conservative mapping. A stale/contradictory event NEVER unlocks access."""
    if not isinstance(proof, ReconciliationProof):
        raise FinancialProofRejected("PROOF_REQUIRED")
    event = proof.notification.event_type
    status = proof.observation.status
    if status == "REFUNDED":
        return "REFUNDED"
    if status == "PARTIALLY_REFUNDED":
        return "PARTIAL_REFUND"
    if status in ("CHARGEBACK_REQUESTED", "CHARGEBACK"):
        return "CHARGEBACK"
    if status in ("CHARGEBACK_DISPUTE", "AWAITING_CHARGEBACK_REVERSAL"):
        return "DISPUTE_OPENED"
    if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED") and status in (
        "CONFIRMED", "RECEIVED"
    ):
        return "CONFIRMED"
    # This includes a refund event against a still-positive GET, stale
    # notifications, unknown/new statuses and cancellation ambiguity.
    return "UNKNOWN"
