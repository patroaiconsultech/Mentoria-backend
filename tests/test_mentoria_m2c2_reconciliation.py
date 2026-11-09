"""M2-C2 focused tests. SQLite is LOGIC ONLY; PostgreSQL not qualified."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from orkio_v2.mentoria.asaas_reconciliation import (
    AsaasReadOnlyPayments, AuthenticatedNotification, ProviderObservation,
    ReconciliationProof, FinancialProofRejected, authenticate_notification,
    verify_and_observe, verified_fact,
)
from orkio_v2.mentoria import financial_ledger
from orkio_v2.mentoria.persistence_models import (
    MentoriaAccessGrant, MentoriaOrder, MentoriaPaymentAttempt, MentoriaProviderEvent,
    MentoriaEnrollment, MentoriaOutbox,
)
from test_mentoria_m2c_fulfillment import engine, seed, NOW, pg_isolated

TOKEN = "correct-auth-token-not-an-api-key-1234"


def webhook(event="PAYMENT_RECEIVED", event_id="evt_a", payment_id="pay_a"):
    return {"id":event_id,"event":event,"payment":{"id":payment_id}}


def remote(payment_id="pay_a", status="RECEIVED", value=1497, reference="ref_a"):
    return {"id":payment_id, "status":status, "value":value, "externalReference":reference}


def make_observation(status="RECEIVED", event="PAYMENT_RECEIVED", amount=149700, ref="ref_a",
                     payment_id="pay_a", event_id="evt_a"):
    return ReconciliationProof(
        notification=AuthenticatedNotification(event_id, event, payment_id),
        observation=ProviderObservation(payment_id, ref, status, amount),
    )


def test_notification_requires_correct_secret():
    assert authenticate_notification(
        header_token=TOKEN, configured_token=TOKEN, payload=webhook()
    ).payment_id=="pay_a"
    for supplied in (None, "bad", TOKEN+"bad"):
        with pytest.raises(FinancialProofRejected, match="WEBHOOK_UNAUTHENTICATED"):
            authenticate_notification(header_token=supplied, configured_token=TOKEN,payload=webhook())


def test_notification_requires_configured_secret():
    for secret in ("", "tiny", "a"*256, "A"*31+" "):
        with pytest.raises(FinancialProofRejected, match="WEBHOOK_NOT_CONFIGURED"):
            authenticate_notification(header_token=secret,configured_token=secret,payload=webhook())


@pytest.mark.parametrize("payload", [{}, [], {"payment":{}}, {"id":"x", "event":"PAYMENT_RECEIVED"},
                                     {"id":"x", "event":"BAD", "payment":{"id":"pay_a"}},
                                     {"id":"x", "event":"PAYMENT_RECEIVED", "payment":{"id":"../oops"}}])
def test_bad_payload_denied(payload):
    with pytest.raises(FinancialProofRejected):
        authenticate_notification(header_token=TOKEN,configured_token=TOKEN,payload=payload)


def test_lookup_is_readonly_pinned_url_and_authenticated():
    def handler(req):
        assert req.method=="GET"
        assert str(req.url)=="https://api-sandbox.asaas.com/v3/payments/pay_a"
        assert req.headers.get("access_token")=="api-key-for-test-only"
        return httpx.Response(200,json=remote())
    client=AsaasReadOnlyPayments(
        api_key="api-key-for-test-only",environment="sandbox",transport=httpx.MockTransport(handler)
    )
    proof=verify_and_observe(
        header_token=TOKEN,configured_token=TOKEN,payload=webhook(),provider=client,
    )
    assert proof.observation.amount_cents==149700
    assert verified_fact(proof)=="CONFIRMED"


@pytest.mark.parametrize("status,expected", [
    ("REFUNDED","REFUNDED"),("PARTIALLY_REFUNDED","PARTIAL_REFUND"),
    ("CHARGEBACK_REQUESTED","CHARGEBACK"),("CHARGEBACK_DISPUTE","DISPUTE_OPENED"),
    ("UNKNOWN_FUTURE","UNKNOWN"),("AWAITING_PAYMENT","UNKNOWN"),
])
def test_status_mapping_is_conservative(status, expected):
    assert verified_fact(make_observation(status=status))==expected


def test_delayed_refund_never_appears_confirmed():
    proof=make_observation(event="PAYMENT_REFUNDED",status="CONFIRMED")
    assert verified_fact(proof)=="UNKNOWN"


@pytest.mark.parametrize("body", [
    remote(value="1497.001"), remote(value=-1),remote(value="NaN"),
    remote(value=True),remote(value="1497",reference=None),
    remote(payment_id="other"),
])
def test_bad_provider_response_denied(body):
    client=AsaasReadOnlyPayments(
        api_key="test", environment="sandbox",
        transport=httpx.MockTransport(lambda req:httpx.Response(200,json=body)),
    )
    with pytest.raises(FinancialProofRejected):
        client.get_payment("pay_a")


@pytest.mark.parametrize("status", [302,401,429,500])
def test_provider_failure_never_confirms(status):
    client=AsaasReadOnlyPayments(
        api_key="test", environment="production",
        transport=httpx.MockTransport(lambda req:httpx.Response(status)),
    )
    with pytest.raises(FinancialProofRejected):
        client.get_payment("pay_a")


def test_bad_payment_id_cannot_change_provider_url():
    client=AsaasReadOnlyPayments(api_key="x",environment="sandbox")
    with pytest.raises(FinancialProofRejected,match="PAYMENT_ID_INVALID"):
        client.get_payment("../admin")
    with pytest.raises(FinancialProofRejected,match="ASAAS_CLIENT_NOT_CONFIGURED"):
        AsaasReadOnlyPayments(api_key="x",environment="other")


def _seed_attempt(db):
    seed(db,financial="AWAITING_PAYMENT",event=False)
    attempt=db.scalar(sa.select(MentoriaPaymentAttempt))
    attempt.provider_payment_id="pay_a"
    attempt.external_reference="ref_a"
    return attempt


@pytest.fixture
def sqlite_ledger(monkeypatch):
    monkeypatch.setattr(financial_ledger,"require_postgres_transaction",lambda _db:None)
    monkeypatch.setenv("MENTORIA_M2C_ENABLED","true")
    monkeypatch.setenv("MENTORIA_M2C2_ENABLED","true")
    # Fulfillment is not invoked for a successful receipt, since M2-C2
    # deliberately does not enroll. For adverse facts, it checks M2-C1 flag.
    from orkio_v2.mentoria import fulfillment
    monkeypatch.setattr(fulfillment,"_require_enabled",lambda _db:None)


def _persist(db, proof, request="test-req"):
    return financial_ledger.persist_verified_event(
        db,proof=proof,request_id=request,now=NOW,
    )


def test_sqlite_guard_fail_closed(engine,monkeypatch):
    with Session(engine) as db:
        with db.begin(): _seed_attempt(db)
        monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
        monkeypatch.setenv("MENTORIA_M2C_ENABLED","true")
        monkeypatch.setenv("MENTORIA_M2C2_ENABLED","true")
        with pytest.raises(RuntimeError,match="POSTGRESQL_ROW_LOCK_REQUIRED"):
            with db.begin(): _persist(db,make_observation())


def test_reconciled_payment_does_not_enroll(engine,sqlite_ledger):
    with Session(engine) as db:
        with db.begin(): _seed_attempt(db)
        with db.begin():
            assert _persist(db,make_observation())=="PAID"
        with db.begin():
            assert _persist(db,make_observation())=="ALREADY_PROCESSED"
            assert db.get(MentoriaOrder,"order").financial_state=="PAID"
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaProviderEvent))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaOutbox))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaEnrollment))==0
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaAccessGrant))==0


def test_mismatch_is_never_paid(engine,sqlite_ledger):
    with Session(engine) as db:
        with db.begin():_seed_attempt(db)
        with db.begin():
            assert _persist(db,make_observation(amount=1))=="REVIEW_REQUIRED"
        with db.begin():
            assert db.get(MentoriaOrder,"order").financial_state=="REVIEW_REQUIRED"


def test_reference_mismatch_rolls_back(engine,sqlite_ledger):
    with Session(engine) as db:
        with db.begin():_seed_attempt(db)
        with pytest.raises(RuntimeError, match="PROVIDER_REFERENCE_MISMATCH"):
            with db.begin():_persist(db,make_observation(ref="other"))
        with db.begin():
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaProviderEvent))==0


def test_rollback_of_financial_record(engine,sqlite_ledger):
    with Session(engine) as db:
        with db.begin():_seed_attempt(db)
        with pytest.raises(RuntimeError,match="simulate"):
            with db.begin():
                assert _persist(db,make_observation())=="PAID"
                raise RuntimeError("simulate")
        with db.begin():
            assert db.get(MentoriaOrder,"order").financial_state=="AWAITING_PAYMENT"
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaProviderEvent))==0


def test_adverse_fact_revokes_no_auto_reactivation(engine,sqlite_ledger):
    from orkio_v2.mentoria import fulfillment as f
    with Session(engine) as db:
        with db.begin():_seed_attempt(db)
        with db.begin():_persist(db,make_observation())
        # Place with SQLite logic-only override for this test; never proof of locks.
        with db.begin():
            def check_datetime(t):
                return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
            original=f._check_datetime
            f._check_datetime=check_datetime
            try:
                assert f.place_reconciled_paid_order(
                    db,tenant_id="mt-a",order_id="order",request_id="r",now=NOW
                ) is not None
            finally:
                f._check_datetime=original
        with db.begin():
            assert _persist(db,make_observation(status="REFUNDED",event_id="evt_b",
                                                event="PAYMENT_REFUNDED"))=="REFUNDED"
        with db.begin():
            assert db.get(MentoriaOrder,"order").financial_state=="REFUNDED"
            assert db.scalar(sa.select(MentoriaAccessGrant)).status=="REVOKED"
            assert db.scalar(sa.select(MentoriaEnrollment)).status=="SUSPENDED"

def test_event_id_provider_can_include_ampersand():
    proof = authenticate_notification(
        header_token=TOKEN, configured_token=TOKEN,
        payload=webhook(event_id="evt_abc&def"),
    )
    assert proof.event_id == "evt_abc&def"


def test_pending_duplicate_event_is_not_reported_as_processed(engine,sqlite_ledger):
    with Session(engine) as db:
        with db.begin():
            _seed_attempt(db)
            db.add(MentoriaProviderEvent(
                id="pending", tenant_id="mt-a", provider="asaas",
                provider_event_id="evt_a", payment_attempt_id="attempt",
                fact_type="UNKNOWN", processed_at=None,
            ))
        with pytest.raises(RuntimeError,match="EVENT_RECONCILIATION_PENDING"):
            with db.begin(): _persist(db,make_observation())
        with db.begin():
            assert db.get(MentoriaOrder,"order").financial_state=="AWAITING_PAYMENT"
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaProviderEvent))==1


def test_pipeline_authenticates_before_db_session_or_lookup():
    from orkio_v2.mentoria.m2c2_pipeline import reconcile_delivery
    calls=[]
    class NoLookup:
        def get_payment(self, _): calls.append("provider"); raise AssertionError("provider not allowed")
    def no_db():
        calls.append("db"); raise AssertionError("DB not allowed")
    with pytest.raises(FinancialProofRejected,match="WEBHOOK_UNAUTHENTICATED"):
        reconcile_delivery(
            session_factory=no_db,provider=NoLookup(),
            auth_token_header="fake",webhook_auth_token=TOKEN,
            payload=webhook(),request_id="r",now=NOW,
        )
    assert calls==[]


def test_pipeline_reads_provider_before_database(engine,sqlite_ledger):
    from orkio_v2.mentoria.m2c2_pipeline import reconcile_delivery
    with Session(engine) as db:
        with db.begin():_seed_attempt(db)
    calls=[]
    class FakeProvider:
        def get_payment(self, _):
            calls.append("provider")
            return ProviderObservation("pay_a","ref_a","RECEIVED",149700)
    def session_factory():
        calls.append("db")
        return Session(engine)
    status=reconcile_delivery(
        session_factory=session_factory,provider=FakeProvider(),
        auth_token_header=TOKEN,webhook_auth_token=TOKEN,
        payload=webhook(),request_id="r",now=NOW,
    )
    assert status=="PAID" and calls==["provider","db"]


def test_ci_workflow_has_manual_sha_pinned_postgres_and_named_pg_tests():
    from pathlib import Path
    workflow=Path(__file__).resolve().parents[1]/".github/workflows/07-mentoria-m2c-postgres-gate.yml"
    data=workflow.read_text()
    assert "workflow_dispatch:" in data
    assert "pull_request:" not in data
    assert "expected_sha" in data and 'git rev-parse HEAD' in data
    assert "postgres:16@sha256:" in data
    assert "- 5432/tcp" in data and "5432:5432" not in data
    assert "job.services.postgres.id" in data
    assert "test_real_pg_reconciled_placement_and_rollback" in data
    assert "test_real_pg_concurrent_same_order_is_idempotent" in data
    assert 'c.find("skipped")' in data

# Real PostgreSQL tests. Skipped unless an explicit disposable CI DB exists.
# SQLite coverage above MUST NOT be promoted as proof of row-level locking.
def test_real_pg_m2c2_reconciliation_dedup(pg_isolated,monkeypatch):
    engine, schema = pg_isolated
    monkeypatch.setenv("MENTORIA_M2C2_ENABLED","true")
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            _seed_attempt(db)
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert _persist(db,make_observation())=="PAID"
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert _persist(db,make_observation())=="ALREADY_PROCESSED"
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaProviderEvent))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaEnrollment))==0


def test_real_pg_m2c2_refund_revokes(pg_isolated,monkeypatch):
    from orkio_v2.mentoria import fulfillment as f
    engine, schema = pg_isolated
    monkeypatch.setenv("MENTORIA_M2C2_ENABLED","true")
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            _seed_attempt(db)
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert _persist(db,make_observation())=="PAID"
            assert f.place_reconciled_paid_order(
                db,tenant_id="mt-a",order_id="order",request_id="place",now=NOW
            ) is not None
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert _persist(db,make_observation(
                status="REFUNDED",event="PAYMENT_REFUNDED",event_id="evt_refund"
            ))=="REFUNDED"
            assert db.scalar(sa.select(MentoriaAccessGrant)).status=="REVOKED"
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert db.scalar(sa.select(MentoriaEnrollment)).status=="SUSPENDED"
            assert db.get(MentoriaOrder,"order").financial_state=="REFUNDED"
