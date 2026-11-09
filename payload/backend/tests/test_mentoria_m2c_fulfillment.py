"""M2-C1 tests. SQLite exercises *logic only*, never PostgreSQL locks.

An opt-in PostgreSQL test in test_mentoria_m2c_postgres.py covers the real
transaction path. Production/provider authenticity remain NOT_PROVEN.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session

from orkio_v2.database import Base
from orkio_v2.models import Tenant
from orkio_v2.mentoria import fulfillment as m2c
from orkio_v2.mentoria.persistence_models import (
    M2B_TABLES, MentoriaAccessGrant, MentoriaAuditEvent, MentoriaCohort,
    MentoriaEnrollment, MentoriaMember, MentoriaOffer, MentoriaOrder,
    MentoriaOutbox, MentoriaPaymentAttempt, MentoriaProgram, MentoriaProviderEvent,
    MentoriaSeatHold,
)

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables["tenants"], *[m.__table__ for m in M2B_TABLES]]
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_logic_only(monkeypatch):
    # Never monkeypatch the production entrypoints. This fixture proves the
    # business transitions only; SQLite FOR UPDATE is not a locking primitive.
    monkeypatch.setattr(m2c, "_require_enabled", lambda _db: None)
    def sqlite_aware(value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return m2c._check_datetime_original(value)  # assigned below
    monkeypatch.setattr(m2c, "_check_datetime_original", m2c._check_datetime, raising=False)
    monkeypatch.setattr(m2c, "_check_datetime", sqlite_aware)


def seed(db, *, hold_ttl=30, financial="PAID", event=True, email_verified=True):
    db.add_all([
        Tenant(id="mt-a",name="Tenant A"),Tenant(id="mt-b",name="Tenant B")
    ])
    db.flush()
    db.add(MentoriaProgram(id="program",tenant_id="mt-a",slug="ia",title="IA",status="PUBLISHED"))
    db.flush()
    db.add(MentoriaCohort(
        id="cohort",tenant_id="mt-a",program_id="program",capacity=1,
        timezone_name="America/Sao_Paulo",
        registration_opens_at=NOW-timedelta(days=1),
        registration_closes_at=NOW+timedelta(days=1),
        starts_at=NOW+timedelta(days=7),ends_at=NOW+timedelta(days=30),
        status="OPEN",
    ))
    db.flush()
    db.add(MentoriaOffer(
        tenant_id="mt-a",id="offer",version=1,cohort_id="cohort",
        program_id="program",amount_cents=149700,currency="BRL",
        access_days=90,terms_version="v1",status="PUBLISHED",
    ))
    db.add(MentoriaMember(
        id="member",tenant_id="mt-a",issuer="trusted-issuer",
        subject="opaque-user",status="ACTIVE",
        email_verified_at=NOW if email_verified else None,
    ))
    db.flush()
    db.add(MentoriaOrder(
        id="order",tenant_id="mt-a",member_id="member",cohort_id="cohort",
        offer_id="offer",offer_version=1,amount_cents=149700,currency="BRL",
        financial_state=financial,fulfillment_state="PENDING",
        idempotency_key_hash="a"*64,request_fingerprint="b"*64,
    ))
    db.flush()
    db.add(MentoriaSeatHold(
        id="hold",tenant_id="mt-a",order_id="order",cohort_id="cohort",
        status="ACTIVE",expires_at=NOW+timedelta(minutes=hold_ttl),
    ))
    db.add(MentoriaPaymentAttempt(
        id="attempt",tenant_id="mt-a",order_id="order",provider="asaas",
        provider_payment_id="pay-" + uuid4().hex,
        external_reference="mentoria-order",
        operation_state="BOUND",
    ))
    db.flush()
    if event:
        db.add(MentoriaProviderEvent(
            id="event",tenant_id="mt-a",provider="asaas",
            provider_event_id="confirmed-" + uuid4().hex,
            payment_attempt_id="attempt",fact_type="CONFIRMED",
            processed_at=NOW,
        ))
    db.flush()


def place(db):
    return m2c.place_reconciled_paid_order(
        db,tenant_id="mt-a",order_id="order",request_id="req-1",now=NOW,
    )


def counts(db):
    return tuple(db.scalar(sa.select(sa.func.count()).select_from(cls)) for cls in (
        MentoriaEnrollment,MentoriaAccessGrant,MentoriaAuditEvent,MentoriaOutbox
    ))


def test_guards_closed_on_sqlite_even_when_features_enabled(engine,monkeypatch):
    monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
    monkeypatch.setenv("MENTORIA_M2C_ENABLED","true")
    with Session(engine) as db, db.begin():
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="POSTGRESQL_ROW_LOCK_REQUIRED"):
            place(db)


def test_guards_closed_without_feature(engine,monkeypatch):
    monkeypatch.delenv("MENTORIA_M2_ENABLED",raising=False)
    with Session(engine) as db, db.begin():
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="M2_FEATURE_DISABLED"):
            place(db)


def test_reconciled_placement_and_idempotence(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():
            placed=place(db)
            assert placed is not None
            assert placed.status=="ACTIVE"
        with db.begin():
            assert place(db).id==placed.id
        with db.begin():
            assert counts(db)==(1,1,1,1)
            assert db.get(MentoriaOrder,"order").fulfillment_state=="ENROLLED"
            assert db.get(MentoriaSeatHold,"hold").status=="CONSUMED"
            grant=db.scalar(sa.select(MentoriaAccessGrant))
            assert grant.status=="ACTIVE"


def test_paid_order_without_processed_event_cannot_place(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db,event=False)
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="PAYMENT_NOT_RECONCILED"):
            with db.begin():place(db)
        with db.begin():assert counts(db)==(0,0,0,0)


def test_unpaid_with_confirmation_cannot_place(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db,financial="AWAITING_PAYMENT")
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="PAYMENT_NOT_RECONCILED"):
            with db.begin():place(db)


def test_email_verification_required(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db,email_verified=False)
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="VERIFIED_MEMBER_REQUIRED"):
            with db.begin():place(db)


def test_wrong_tenant_never_places(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="ORDER_UNAVAILABLE"):
            with db.begin():
                m2c.place_reconciled_paid_order(
                    db,tenant_id="mt-b",order_id="order",request_id="r",now=NOW
                )
        with db.begin():assert counts(db)==(0,0,0,0)


def test_expired_hold_generates_no_grant_and_paid_unplaced_once(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db,hold_ttl=-1)
        with db.begin():assert place(db) is None
        with db.begin():assert place(db) is None
        with db.begin():
            assert counts(db)==(0,0,1,1)
            assert db.get(MentoriaOrder,"order").fulfillment_state=="PAID_UNPLACED"
            assert db.get(MentoriaSeatHold,"hold").status=="EXPIRED"


def test_offer_price_change_blocks_grant(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():db.get(MentoriaOffer,{"tenant_id":"mt-a","id":"offer","version":1}).amount_cents=9999
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="ORDER_PRICE_SNAPSHOT_MISMATCH"):
            with db.begin():place(db)


def test_adverse_refund_revokes_and_never_reopens(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():place(db)
        with db.begin():
            db.get(MentoriaOrder,"order").financial_state="REFUNDED"
            db.add(MentoriaProviderEvent(
                id="event-adverse",tenant_id="mt-a",provider="asaas",
                provider_event_id="ref-" + uuid4().hex,
                payment_attempt_id="attempt",fact_type="REFUNDED",
                processed_at=NOW+timedelta(minutes=1),
            ))
        with db.begin():
            assert m2c.suspend_after_reconciled_adverse_fact(
                db,tenant_id="mt-a",order_id="order",request_id="r2",
                now=NOW+timedelta(minutes=2),
            ) is True
        with db.begin():
            assert m2c.suspend_after_reconciled_adverse_fact(
                db,tenant_id="mt-a",order_id="order",request_id="r3",
                now=NOW+timedelta(minutes=3),
            ) is True
            assert counts(db)==(1,1,2,2)
            assert db.scalar(sa.select(MentoriaAccessGrant)).status=="REVOKED"
            assert db.scalar(sa.select(MentoriaEnrollment)).status=="SUSPENDED"
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="PAYMENT_NOT_RECONCILED"):
            with db.begin():place(db)


def test_adverse_event_required_for_suspension(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():place(db)
        with db.begin():db.get(MentoriaOrder,"order").financial_state="DISPUTED"
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="ADVERSE_EVENT_NOT_RECONCILED"):
            with db.begin():
                m2c.suspend_after_reconciled_adverse_fact(
                    db,tenant_id="mt-a",order_id="order",request_id="r2",now=NOW
                )


def test_transaction_rollback_has_no_partial_placement(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with pytest.raises(RuntimeError,match="simulate"):
            with db.begin():
                place(db)
                raise RuntimeError("simulate")
        with db.begin():
            assert counts(db)==(0,0,0,0)
            assert db.get(MentoriaOrder,"order").fulfillment_state=="PENDING"
            assert db.get(MentoriaSeatHold,"hold").status=="ACTIVE"



def test_bound_attempt_with_empty_provider_payment_id_is_not_proof(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():
            db.get(MentoriaPaymentAttempt,"attempt").provider_payment_id=""
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="PAYMENT_NOT_RECONCILED"):
            with db.begin():place(db)


def test_idempotent_placement_denies_revoked_member(engine,sqlite_logic_only):
    with Session(engine) as db:
        with db.begin():seed(db)
        with db.begin():assert place(db) is not None
        with db.begin():db.get(MentoriaMember,"member").status="REVOKED"
        with pytest.raises(m2c.MentoriaFulfillmentStop,match="ENROLLMENT_INCONSISTENT"):
            with db.begin():place(db)

# --- Opt-in REAL PostgreSQL qualification: NOT exercised on SQLite. ---
# Dedicated empty database name must end in "_m2c_test". Never point this
# fixture at a live/staging database or a database holding other workloads.

@pytest.fixture
def pg_isolated(monkeypatch):
    import os
    from sqlalchemy.engine.url import make_url
    from uuid import uuid4
    url = os.getenv("MENTORIA_M2C_TEST_DATABASE_URL")
    if not url or os.getenv("MENTORIA_M2C_ALLOW_SCHEMA_TEST") != "true":
        pytest.skip("M2-C disposable PostgreSQL not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (
        parsed.database and parsed.database.endswith("_m2c_test")
    ):
        pytest.fail("M2C refuses non-disposable test database")
    engine = sa.create_engine(url, pool_size=4, max_overflow=2)
    schema = "m2c_" + uuid4().hex[:16]
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(
                conn, tables=[Base.metadata.tables["tenants"], *[m.__table__ for m in M2B_TABLES]]
            )
        monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
        monkeypatch.setenv("MENTORIA_M2C_ENABLED","true")
        yield engine, schema
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _session_with_schema(engine, schema):
    db = Session(engine)
    return db


def test_real_pg_reconciled_placement_and_rollback(pg_isolated):
    engine, schema = pg_isolated
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            seed(db)
    with Session(engine) as db:
        with pytest.raises(RuntimeError, match="rollback-test"):
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                assert place(db) is not None
                raise RuntimeError("rollback-test")
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert counts(db) == (0,0,0,0)
            assert place(db) is not None
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert counts(db) == (1,1,1,1)
            assert place(db).status == "ACTIVE"
            assert counts(db) == (1,1,1,1)


def test_real_pg_concurrent_same_order_is_idempotent(pg_isolated):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine, schema = pg_isolated
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            seed(db)
    barrier=Barrier(2)
    def attempt():
        with Session(engine) as db:
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                barrier.wait(timeout=12)
                result=place(db)
                return result.id
    with ThreadPoolExecutor(max_workers=2) as executor:
        a=executor.submit(attempt); b=executor.submit(attempt)
        assert a.result(timeout=30) == b.result(timeout=30)
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert counts(db)==(1,1,1,1)
