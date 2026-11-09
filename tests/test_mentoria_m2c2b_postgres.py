"""REAL PostgreSQL only. Default SKIP, never touch operational databases.

Required: MENTORIA_M2C_TEST_DATABASE_URL ending *_m2c_test, localhost only,
MENTORIA_M2C2B_PG_ALLOW=true, MENTORIA_M2_ENABLED=true and MENTORIA_M2C2B_ENABLED=true.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from orkio_v2.database import Base
from orkio_v2.models import Tenant
from orkio_v2.mentoria.asaas_reconciliation import AuthenticatedNotification
from orkio_v2.mentoria.m2c2b_ingress import record_authenticated_delivery
from orkio_v2.mentoria.persistence_models import (
    M2B_TABLES, MentoriaWebhookInbox, MentoriaProgram, MentoriaCohort,
    MentoriaOffer, MentoriaMember, MentoriaOrder, MentoriaPaymentAttempt,
)


@pytest.fixture()
def disposable_pg(monkeypatch):
    url = os.getenv("MENTORIA_M2C_TEST_DATABASE_URL")
    if os.getenv("MENTORIA_M2C2B_PG_ALLOW") != "true" or not url:
        pytest.skip("M2-C2B requires isolated, explicit PostgreSQL test authorization")
    parsed = make_url(url)
    if (parsed.get_backend_name() != "postgresql" or parsed.host not in ("127.0.0.1", "localhost")
        or not parsed.database or not parsed.database.endswith("_m2c_test")):
        pytest.fail("STOP: refusing non-local or non-disposable PostgreSQL")
    engine = sa.create_engine(url, pool_size=4, max_overflow=2)
    schema = "m2c2b_" + uuid4().hex[:12]
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            Base.metadata.create_all(conn, tables=[
                Tenant.__table__, *[model.__table__ for model in M2B_TABLES],
            ])
            path = Path(__file__).resolve().parents[1] / "migrations/versions/019_mentoria_webhook_inbox.py"
            spec = spec_from_file_location("mentoria_pg_019", path)
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            module.op = Operations(MigrationContext.configure(conn))
            module.upgrade()
            assert sa.inspect(conn).has_table("mentoria_webhook_inbox")
        monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
        monkeypatch.setenv("MENTORIA_M2C2B_ENABLED","true")
        yield engine, schema
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()


def _seed(engine, schema, now):
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            db.add(Tenant(id="tenant-a",name="Test tenant"))
            db.flush()
            db.add(MentoriaProgram(id="program",tenant_id="tenant-a",slug="mentoria",title="Test",status="PUBLISHED"))
            db.flush()
            db.add(MentoriaCohort(
                id="cohort",tenant_id="tenant-a",program_id="program",capacity=2,
                timezone_name="UTC",registration_opens_at=now-timedelta(days=1),
                registration_closes_at=now+timedelta(days=1),
                starts_at=now+timedelta(days=3),ends_at=now+timedelta(days=5),
                status="OPEN",
            ))
            db.flush()
            db.add(MentoriaOffer(
                tenant_id="tenant-a",id="offer",version=1,cohort_id="cohort",program_id="program",
                amount_cents=149700,currency="BRL",access_days=90,terms_version="v1",status="PUBLISHED",
            ))
            db.add(MentoriaMember(id="member",tenant_id="tenant-a",issuer="test",subject="u1",status="ACTIVE"))
            db.flush()
            db.add(MentoriaOrder(
                id="order",tenant_id="tenant-a",member_id="member",cohort_id="cohort",
                offer_id="offer",offer_version=1,amount_cents=149700,currency="BRL",
                financial_state="AWAITING_PAYMENT",fulfillment_state="PENDING",
                idempotency_key_hash="a"*64,request_fingerprint="b"*64,
            ))
            db.flush()
            db.add(MentoriaPaymentAttempt(
                id="attempt",tenant_id="tenant-a",order_id="order",provider="asaas",
                provider_payment_id="pay_1",external_reference="ref_1",operation_state="BOUND",
            ))


def test_real_pg_webhook_duplicate_two_connections(disposable_pg):
    engine, schema = disposable_pg
    now = datetime.now(timezone.utc)
    _seed(engine, schema, now)
    notification = AuthenticatedNotification("evt_1","PAYMENT_RECEIVED","pay_1")
    gate = Barrier(2)
    def receive():
        with Session(engine) as db:
            gate.wait(timeout=8)
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                return record_authenticated_delivery(db, notification=notification, now=now)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1=ex.submit(receive); f2=ex.submit(receive)
        results=[f1.result(timeout=20),f2.result(timeout=20)]
    assert sorted(results) == ["DUPLICATE_RECEIPT","DURABLY_RECORDED"]
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaWebhookInbox)) == 1


def test_real_pg_receipt_failure_rolls_back(disposable_pg):
    engine, schema = disposable_pg
    now = datetime.now(timezone.utc)
    _seed(engine, schema, now)
    notification = AuthenticatedNotification("evt_rollback", "PAYMENT_RECEIVED", "pay_1")
    with pytest.raises(RuntimeError,match="INJECTED_TEST_FAILURE"):
        with Session(engine) as db:
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                record_authenticated_delivery(db, notification=notification, now=now)
                raise RuntimeError("INJECTED_TEST_FAILURE")
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaWebhookInbox)) == 0
