"""M2-A: testes PUROS, sem provedor/DB/auth HTTP. Não equivalem a E2E."""

from datetime import datetime, timedelta, timezone

import pytest

from orkio_v2.mentoria.domain_contracts import (
    AccessSnapshot, ContractViolation, EnrollmentStatus, FinancialFact,
    FinancialState, GrantStatus, PriceSnapshot, allows_mentoria_access,
    next_financial_state, order_payload_fingerprint, seat_available,
)

NOW = datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
PRICE = PriceSnapshot(
    tenant_id="tenant-mentoria", offer_id="offer-1",
    cohort_id="cohort-2026", offer_version=1, amount_cents=149700,
)


def change(state, fact, amount=149700, currency="BRL"):
    return next_financial_state(
        state, fact, snapshot=PRICE,
        observed_amount_cents=amount, observed_currency=currency,
    )


@pytest.mark.parametrize(
    ("current", "fact", "expected"),
    [
        (FinancialState.CREATED, FinancialFact.PENDING, FinancialState.AWAITING_PAYMENT),
        (FinancialState.AWAITING_PAYMENT, FinancialFact.CONFIRMED, FinancialState.PAID),
        (FinancialState.PAID, FinancialFact.CONFIRMED, FinancialState.PAID),
        (FinancialState.PAID, FinancialFact.PENDING, FinancialState.PAID),
        (FinancialState.CREATED, FinancialFact.REFUNDED, FinancialState.REFUNDED),
        (FinancialState.PAID, FinancialFact.REFUNDED, FinancialState.REFUNDED),
        (FinancialState.REFUNDED, FinancialFact.CONFIRMED, FinancialState.REFUNDED),
        (FinancialState.CHARGEBACK, FinancialFact.CONFIRMED, FinancialState.CHARGEBACK),
        (FinancialState.PAID, FinancialFact.CHARGEBACK, FinancialState.CHARGEBACK),
        (FinancialState.PAID, FinancialFact.DISPUTE_OPENED, FinancialState.DISPUTED),
        (FinancialState.DISPUTED, FinancialFact.CONFIRMED, FinancialState.REVIEW_REQUIRED),
        (FinancialState.DISPUTED, FinancialFact.DISPUTE_RESOLVED, FinancialState.REVIEW_REQUIRED),
        (FinancialState.PAID, FinancialFact.PARTIAL_REFUND, FinancialState.REVIEW_REQUIRED),
        (FinancialState.PAID, FinancialFact.UNKNOWN, FinancialState.REVIEW_REQUIRED),
        (FinancialState.CREATED, FinancialFact.CANCELLED, FinancialState.CANCELLED),
        (FinancialState.AWAITING_PAYMENT, FinancialFact.EXPIRED, FinancialState.EXPIRED),
        (FinancialState.PAID, FinancialFact.CANCELLED, FinancialState.REVIEW_REQUIRED),
        (FinancialState.EXPIRED, FinancialFact.CONFIRMED, FinancialState.REVIEW_REQUIRED),
    ],
)
def test_financial_transition_is_conservative(current, fact, expected):
    assert change(current, fact) == expected


@pytest.mark.parametrize(("amount", "currency"), [
    (149699, "BRL"), (149701, "BRL"), (149700, "USD"),
    (None, "BRL"), (149700.0, "BRL"), (True, "BRL"),
])
def test_amount_or_currency_mismatch_never_confirms(amount, currency):
    assert change(FinancialState.AWAITING_PAYMENT, FinancialFact.CONFIRMED, amount, currency) == FinancialState.REVIEW_REQUIRED


@pytest.mark.parametrize("amount", [0, -1, True, 149700.0, "149700"])
def test_price_snapshot_denies_invalid_cents(amount):
    with pytest.raises(ContractViolation):
        PriceSnapshot(
            tenant_id="tenant-mentoria", offer_id="offer-1",
            cohort_id="cohort-2026", offer_version=1,
            amount_cents=amount,
        )


def test_price_snapshot_denies_wrong_currency():
    with pytest.raises(ContractViolation):
        PriceSnapshot(
            tenant_id="tenant-mentoria", offer_id="offer-1",
            cohort_id="cohort-2026", offer_version=1,
            amount_cents=100, currency="USD",
        )


def test_fingerprint_is_stable_but_scoped():
    params = {
        "tenant_id": "t1", "buyer_subject_id": "buyerA",
        "offer_id": "offer1", "offer_version": 1, "cohort_id": "cohort1",
    }
    fingerprint = order_payload_fingerprint(**params)
    assert fingerprint == order_payload_fingerprint(**params)
    assert fingerprint != order_payload_fingerprint(**(params | {"buyer_subject_id": "buyerB"}))
    assert fingerprint != order_payload_fingerprint(**(params | {"tenant_id": "t2"}))
    assert fingerprint != order_payload_fingerprint(**(params | {"offer_version": 2}))


@pytest.mark.parametrize(("active", "holds", "expected"), [
    (0, 0, True), (45, 4, True), (45, 5, False), (50, 0, False),
])
def test_capacity_predicate(active, holds, expected):
    assert seat_available(capacity=50, active_enrollments=active, live_holds=holds) is expected


def test_invalid_seat_inputs_denied():
    with pytest.raises(ContractViolation):
        seat_available(capacity=0, active_enrollments=0, live_holds=0)
    with pytest.raises(ContractViolation):
        seat_available(capacity=50, active_enrollments=-1, live_holds=0)


def access_snapshot(**changes):
    values = {
        "tenant_id": "tenant-mentoria",
        "buyer_subject_id": "subject-1",
        "cohort_id": "cohort-2026",
        "financial_state": FinancialState.PAID,
        "enrollment_status": EnrollmentStatus.ACTIVE,
        "grant_status": GrantStatus.ACTIVE,
        "grant_starts_at": NOW - timedelta(days=1),
        "grant_expires_at": NOW + timedelta(days=30),
        "revoked_at": None,
    }
    return AccessSnapshot(**(values | changes))


def decision(snap, **change):
    vals = {
        "principal_subject_id": "subject-1",
        "owner_tenant_id": "tenant-mentoria",
        "requested_cohort_id": "cohort-2026",
        "snapshot": snap,
        "now": NOW,
    }
    return allows_mentoria_access(**(vals | change))


def test_valid_paid_active_grant_can_access():
    assert decision(access_snapshot())


@pytest.mark.parametrize("mutations", [
    {"tenant_id": "outro-tenant"},
    {"buyer_subject_id": "outro-usuario"},
    {"cohort_id": "outra-turma"},
    {"financial_state": FinancialState.AWAITING_PAYMENT},
    {"financial_state": FinancialState.REFUNDED},
    {"financial_state": FinancialState.REVIEW_REQUIRED},
    {"financial_state": FinancialState.DISPUTED},
    {"financial_state": FinancialState.CHARGEBACK},
    {"enrollment_status": EnrollmentStatus.SUSPENDED},
    {"grant_status": GrantStatus.REVOKED},
    {"grant_status": GrantStatus.EXPIRED},
    {"revoked_at": NOW},
    {"grant_starts_at": NOW + timedelta(seconds=1)},
    {"grant_expires_at": NOW},
    {"grant_expires_at": NOW - timedelta(seconds=1)},
    {"grant_expires_at": datetime(2026, 11, 5)},
])
def test_access_fail_closed_if_any_invariant_breaks(mutations):
    assert not decision(access_snapshot(**mutations))


def test_wrong_authenticated_subject_always_denied():
    assert not decision(access_snapshot(), principal_subject_id="subject-2")


def test_empty_and_missing_snapshot_denied():
    assert not decision(None)
    assert not decision(access_snapshot(), owner_tenant_id="")
    assert not decision(access_snapshot(), principal_subject_id="")


def test_financial_reducer_rejects_unknown_typed_source():
    with pytest.raises(ContractViolation):
        next_financial_state("PAID", FinancialFact.CONFIRMED, snapshot=PRICE)
    with pytest.raises(ContractViolation):
        next_financial_state(FinancialState.PAID, "CONFIRMED", snapshot=PRICE)
