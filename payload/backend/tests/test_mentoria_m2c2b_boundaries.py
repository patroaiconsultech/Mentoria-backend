"""M2-C2B focused isolated tests (not evidence of PostgreSQL/runtime)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orkio_v2.auth import Principal, require_principal
from orkio_v2.database import get_db
from orkio_v2.mentoria import m2c2b_buyer as buyer
from orkio_v2.mentoria import m2c2b_http as http
from orkio_v2.mentoria import m2c2b_ingress as ingress
from orkio_v2.mentoria import m2c2b_worker as worker
from orkio_v2.mentoria.asaas_reconciliation import AuthenticatedNotification
from orkio_v2.mentoria.persistence_models import MentoriaMember, MentoriaPaymentAttempt

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
TOKEN = "a" * 48


class BuyerDB:
    def __init__(self, *, user=True, membership=True, member=True, verified=True):
        self.user = NS(
            id="user-A", external_subject="native:member@example.org",
            email_verified_at=NOW if verified else None,
        ) if user else None
        self.membership = NS(tenant_id="tenant-A", user_id="user-A", active=True) if membership else None
        self.member = NS(tenant_id="tenant-A", issuer=buyer.CANONICAL_MEMBER_ISSUER,
                         subject="user-A", status="ACTIVE",
                         email_verified_at=NOW) if member else None
    def get(self, model, identity):
        return self.user if identity == "user-A" else None
    def scalar(self, query):
        sql = str(query)
        return self.membership if "memberships" in sql else self.member


PRINCIPAL = Principal(
    user_id="user-A", tenant_id="tenant-A", roles=("member",),
    email="member@example.org", external_subject="native:member@example.org",
)


@pytest.mark.parametrize("kwargs", [
    {"user": False}, {"membership": False}, {"member": False}, {"verified": False},
])
def test_buyer_denies_missing_canonical_links(kwargs):
    with pytest.raises(buyer.BuyerIdentityDenied):
        buyer.verified_buyer(BuyerDB(**kwargs), PRINCIPAL)


def test_buyer_rejects_subject_spoof_or_tenant_spoof():
    for altered in [
        replace(PRINCIPAL, external_subject="attacker"),
        replace(PRINCIPAL, tenant_id="attacker"),
    ]:
        with pytest.raises(buyer.BuyerIdentityDenied):
            buyer.verified_buyer(BuyerDB(), altered)


def test_buyer_maps_canonical_identity_only():
    result = buyer.verified_buyer(BuyerDB(), PRINCIPAL)
    assert result.tenant_id == "tenant-A"
    assert result.issuer == buyer.CANONICAL_MEMBER_ISSUER
    assert result.subject == "user-A"


def test_ingress_fingerprint_is_stable_and_event_bound():
    n = AuthenticatedNotification("evt-1", "PAYMENT_CONFIRMED", "pay-1")
    assert ingress.receipt_fingerprint(n) == ingress.receipt_fingerprint(n)
    assert ingress.receipt_fingerprint(n) != ingress.receipt_fingerprint(
        AuthenticatedNotification("evt-1", "PAYMENT_REFUNDED", "pay-1")
    )


class MemoryIngressDB:
    def __init__(self, *, bound=True, existing=None):
        self.bound = bound
        self.receipt = existing
        self.pending = []
    def scalar(self, q):
        sql = str(q)
        if "mentoria_payment_attempts" in sql:
            return NS(id="attempt-1", tenant_id="tenant-A") if self.bound else None
        if "mentoria_webhook_inbox" in sql:
            return self.receipt
        raise AssertionError(sql)
    def add(self, item):
        self.pending.append(item)
    def flush(self):
        pass


@pytest.fixture
def fake_pg(monkeypatch):
    monkeypatch.setenv("MENTORIA_M2C2B_ENABLED", "true")
    monkeypatch.setattr(ingress, "require_postgres_transaction", lambda db: None)


def test_new_authenticated_receipt_is_sanitized(fake_pg):
    db = MemoryIngressDB()
    n = AuthenticatedNotification("evt-1", "PAYMENT_CONFIRMED", "pay-1")
    assert ingress.record_authenticated_delivery(db, notification=n, now=NOW) == "DURABLY_RECORDED"
    r = db.pending[0]
    assert r.tenant_id == "tenant-A"
    assert r.payment_id == "pay-1"
    assert r.status == "PENDING"
    assert not hasattr(r, "raw_payload")
    assert not hasattr(r, "token")


def test_unbound_payment_cannot_be_acknowledged(fake_pg):
    db = MemoryIngressDB(bound=False)
    with pytest.raises(ingress.WebhookIngressStopped, match="UNBOUND_PAYMENT"):
        ingress.record_authenticated_delivery(
            db, notification=AuthenticatedNotification("evt-1", "PAYMENT_CONFIRMED", "pay-1"), now=NOW
        )
    assert not db.pending


def test_matching_duplicate_is_idempotent(fake_pg):
    n = AuthenticatedNotification("evt-1", "PAYMENT_CONFIRMED", "pay-1")
    existing = NS(tenant_id="tenant-A", payment_attempt_id="attempt-1",
                  payment_id="pay-1", event_fingerprint=ingress.receipt_fingerprint(n))
    db = MemoryIngressDB(existing=existing)
    assert ingress.record_authenticated_delivery(db, notification=n, now=NOW) == "DUPLICATE_RECEIPT"
    assert not db.pending


def test_contradictory_replay_never_acknowledged(fake_pg):
    original = AuthenticatedNotification("evt-1", "PAYMENT_CONFIRMED", "pay-1")
    changed = AuthenticatedNotification("evt-1", "PAYMENT_REFUNDED", "pay-1")
    db = MemoryIngressDB(existing=NS(
        tenant_id="tenant-A", payment_attempt_id="attempt-1",
        payment_id="pay-1", event_fingerprint=ingress.receipt_fingerprint(original),
    ))
    with pytest.raises(ingress.WebhookIngressStopped, match="CONTRADICTORY_REPLAY"):
        ingress.record_authenticated_delivery(db, notification=changed, now=NOW)


def test_not_authenticated_does_not_reach_persistence(monkeypatch):
    monkeypatch.setattr(http, "get_settings", lambda: NS(
        mentoria_m2c2b_enabled=True, mentoria_asaas_webhook_token=TOKEN))
    monkeypatch.setattr(http, "ingress_enabled", lambda: True)
    calls = []
    monkeypatch.setattr(http, "_persist_receipt", lambda n: calls.append(n))
    app = FastAPI()
    app.include_router(http.router)
    c = TestClient(app)
    payload = {"id": "evt-1", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay-1"}}
    assert c.post(http.WEBHOOK_PATH, json=payload).status_code == 401
    assert c.post(http.WEBHOOK_PATH, json=payload, headers={
        "asaas-access-token": "WRONG"}).status_code == 401
    assert calls == []


def test_authenticated_ingress_ack_after_commit_success(monkeypatch):
    monkeypatch.setattr(http, "get_settings", lambda: NS(
        mentoria_m2c2b_enabled=True, mentoria_asaas_webhook_token=TOKEN))
    monkeypatch.setattr(http, "ingress_enabled", lambda: True)
    received = []
    monkeypatch.setattr(http, "_persist_receipt", lambda n: received.append(n))
    app = FastAPI()
    app.include_router(http.router)
    c = TestClient(app)
    payload = {"id": "evt-1", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay-1"}}
    result = c.post(http.WEBHOOK_PATH, json=payload, headers={"asaas-access-token": TOKEN})
    assert result.status_code == 200
    assert len(received) == 1 and received[0].payment_id == "pay-1"


def test_persistence_failure_is_not_acknowledged(monkeypatch):
    monkeypatch.setattr(http, "get_settings", lambda: NS(
        mentoria_m2c2b_enabled=True, mentoria_asaas_webhook_token=TOKEN))
    monkeypatch.setattr(http, "ingress_enabled", lambda: True)
    def fail(n):
        raise ingress.WebhookIngressStopped("UNBOUND_PAYMENT")
    monkeypatch.setattr(http, "_persist_receipt", fail)
    app = FastAPI()
    app.include_router(http.router)
    c = TestClient(app)
    result = c.post(http.WEBHOOK_PATH, json={
        "id": "evt-1", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay-1"},
    }, headers={"asaas-access-token": TOKEN})
    assert result.status_code == 503


def test_inbound_body_is_bounded_and_invalid_event_rejected(monkeypatch):
    monkeypatch.setattr(http, "get_settings", lambda: NS(
        mentoria_m2c2b_enabled=True, mentoria_asaas_webhook_token=TOKEN))
    monkeypatch.setattr(http, "ingress_enabled", lambda: True)
    app = FastAPI()
    app.include_router(http.router)
    c = TestClient(app)
    assert c.post(http.WEBHOOK_PATH, content="x" * 40000,
                  headers={"content-type": "application/json",
                           "asaas-access-token": TOKEN}).status_code == 413
    assert c.post(http.WEBHOOK_PATH, json={"id":"evt-1","event":"ADMIN_ADDED","payment":{"id":"pay-1"}},
                  headers={"asaas-access-token": TOKEN}).status_code == 400


def test_buyer_endpoint_delegates_to_canonical_auth(monkeypatch):
    monkeypatch.setattr(http, "get_settings", lambda: NS(mentoria_m2c2b_enabled=True))
    app = FastAPI()
    app.include_router(http.router)
    app.dependency_overrides[require_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_db] = lambda: BuyerDB()
    c = TestClient(app)
    assert c.get("/api/v2/mentoria/buyer/me").json() == {"status": "ready"}
    app.dependency_overrides[require_principal] = lambda: replace(PRINCIPAL, tenant_id="attacker")
    assert c.get("/api/v2/mentoria/buyer/me").status_code == 403


def test_worker_attempt_lease_no_stale_release(monkeypatch):
    monkeypatch.setattr(worker, "require_postgres_transaction", lambda db: None)
    class DB:
        receipt = NS(id="x", status="PROCESSING", attempt_count=2)
    monkeypatch.setattr(worker, "_select_receipt", lambda db, receipt_id: db.receipt)
    with pytest.raises(worker.WorkerStopped, match="LEASE_CHANGED"):
        worker._fail(DB(), receipt_id="x", attempt_number=1,
                     now=NOW, code="PROVIDER_PROOF_INVALID", retry=False)


class WorkerFakeDB:
    def __init__(self):
        self.inbox = NS(
            id="inbox-1", status="PROCESSING", tenant_id="tenant-A",
            payment_attempt_id="attempt-1", attempt_count=1, provider_event_id="evt-1",
            processed_at=None, leased_at=NOW,
        )
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def begin(self): return self
    def flush(self): return None
    def scalar(self, query):
        return NS(id="attempt-1", tenant_id="tenant-A", provider="asaas",
                  provider_payment_id="pay-1", operation_state="BOUND")


def test_worker_reads_provider_between_claim_and_ledger(monkeypatch):
    from orkio_v2.mentoria.asaas_reconciliation import ProviderObservation
    actions = []
    monkeypatch.setattr(worker, "ingress_enabled", lambda: True)
    monkeypatch.setattr(worker, "require_postgres_transaction", lambda db: None)
    monkeypatch.setattr(worker, "_select_receipt", lambda db, receipt_id: db.inbox)
    monkeypatch.setattr(worker, "_claim", lambda db, **kw: (
        actions.append("claim") or ("tenant-A", "evt-1", "PAYMENT_RECEIVED", "pay-1", "attempt-1", 1)
    ))
    class FakeProvider:
        def get_payment(self, pid):
            actions.append("provider")
            assert pid == "pay-1"
            return ProviderObservation("pay-1", "ref-1", "RECEIVED", 149700)
    def fake_persist(db, **kw):
        actions.append("ledger")
        assert kw["proof"].notification.event_id == "evt-1"
        return "PAID"
    monkeypatch.setattr(worker, "persist_verified_event", fake_persist)
    db = WorkerFakeDB()
    status = worker.process_one(
        receipt_id="inbox-1", session_factory=lambda: db,
        provider=FakeProvider(), now=NOW, request_id="req-1",
    )
    assert status == "PAID"
    assert actions == ["claim", "provider", "ledger"]
    assert db.inbox.status == "PROCESSED"


def test_worker_transient_provider_failure_keeps_retry(monkeypatch):
    from orkio_v2.mentoria.asaas_reconciliation import FinancialProofRejected
    monkeypatch.setattr(worker, "ingress_enabled", lambda: True)
    monkeypatch.setattr(worker, "_claim", lambda db, **kw:
        ("tenant-A", "evt-1", "PAYMENT_RECEIVED", "pay-1", "attempt-1", 1))
    actions=[]
    monkeypatch.setattr(worker, "_fail", lambda db, **kw: actions.append(kw))
    class Offline:
        def get_payment(self, pid):
            raise FinancialProofRejected("ASAAS_LOOKUP_FAILED")
    assert worker.process_one(
        receipt_id="inbox-1", session_factory=WorkerFakeDB,
        provider=Offline(), now=NOW, request_id="req-1",
    ) == "RETRY_OR_REVIEW"
    assert actions[0]["retry"] is True
    assert actions[0]["attempt_number"] == 1


def test_worker_financial_conflict_stays_review(monkeypatch):
    from orkio_v2.mentoria.asaas_reconciliation import ProviderObservation
    from orkio_v2.mentoria.financial_ledger import ReconciliationStopped
    monkeypatch.setattr(worker, "ingress_enabled", lambda: True)
    monkeypatch.setattr(worker, "_claim", lambda db, **kw:
        ("tenant-A", "evt-1", "PAYMENT_RECEIVED", "pay-1", "attempt-1", 1))
    monkeypatch.setattr(worker, "require_postgres_transaction", lambda db: None)
    monkeypatch.setattr(worker, "_select_receipt", lambda db, rid: db.inbox)
    actions = []
    monkeypatch.setattr(worker, "_fail", lambda db, **kw: actions.append(kw))
    class FakeProvider:
        def get_payment(self, pid):
            return ProviderObservation("pay-1", "ref-1", "RECEIVED", 149700)
    def reject(*args, **kwargs):
        raise ReconciliationStopped("FINANCIAL_STATE_INVALID")
    monkeypatch.setattr(worker, "persist_verified_event", reject)
    assert worker.process_one(
        receipt_id="inbox-1", session_factory=WorkerFakeDB,
        provider=FakeProvider(), now=NOW, request_id="req-1",
    ) == "REVIEW"
    assert actions[0]["retry"] is False
