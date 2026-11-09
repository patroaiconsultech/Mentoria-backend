"""M2-B local SQLite constraints/DDL; NOT a PostgreSQL concurrency proof."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orkio_v2.database import Base
from orkio_v2.models import Tenant
from orkio_v2.mentoria.persistence_models import (
    M2B_TABLES, MentoriaProgram, MentoriaCohort, MentoriaMember,
    MentoriaOffer, MentoriaOrder, MentoriaPaymentAttempt,
    MentoriaProviderEvent, MentoriaEnrollment, MentoriaAccessGrant,
    MentoriaSeatHold, MentoriaAuditEvent, MentoriaOutbox,
)
from orkio_v2.mentoria.transactional_repository import (
    VerifiedMentoriaIdentity, MentoriaPersistenceStop, reserve_checkout_order,
)


@pytest.fixture()
def engine():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def enforce_fk(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine, tables=[
        Base.metadata.tables["tenants"], *[m.__table__ for m in M2B_TABLES],
    ])
    try:
        yield engine
    finally:
        engine.dispose()


def t0():
    return datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def populate(session: Session):
    ts = t0()
    session.add_all([Tenant(id="tenant-A",name="A"),Tenant(id="tenant-B",name="B")])
    session.flush()
    session.add(MentoriaProgram(id="program",tenant_id="tenant-A",slug="ia",title="IA",status="PUBLISHED"))
    session.flush()
    session.add(MentoriaCohort(
        id="cohort",tenant_id="tenant-A",program_id="program",capacity=1,timezone_name="America/Sao_Paulo",
        registration_opens_at=ts-timedelta(days=1), registration_closes_at=ts+timedelta(days=1),
        starts_at=ts+timedelta(days=10),ends_at=ts+timedelta(days=20),status="OPEN",
    ))
    session.flush()
    session.add(MentoriaOffer(
        id="offer",tenant_id="tenant-A",cohort_id="cohort",program_id="program",version=1,
        amount_cents=149700,currency="BRL",access_days=90,terms_version="v1",status="PUBLISHED",
    ))
    session.add(MentoriaMember(id="member",tenant_id="tenant-A",issuer="issuer.example",
                               subject="verified-subject",status="ACTIVE"))
    session.flush()


def make_order(**overrides):
    values=dict(
        id=str(uuid4()),tenant_id="tenant-A",member_id="member",cohort_id="cohort",
        offer_id="offer",offer_version=1,amount_cents=149700,currency="BRL",
        financial_state="CREATED",fulfillment_state="PENDING",
        idempotency_key_hash=uuid4().hex+uuid4().hex,
        request_fingerprint=uuid4().hex+uuid4().hex,
    )
    values.update(overrides)
    return MentoriaOrder(**values)


def test_twelve_tables_create_with_canonical_metadata(engine):
    names=sa.inspect(engine).get_table_names()
    assert all(cls.__table__.name in names for cls in M2B_TABLES)
    assert len(M2B_TABLES)==12


@pytest.mark.parametrize("bad",[
    dict(tenant_id="tenant-B"),
    dict(member_id="foreign-member"),
    dict(cohort_id="foreign-cohort"),
    dict(offer_version=20),
    dict(amount_cents=0),
    dict(currency="USD"),
    dict(financial_state="FREE"),
])
def test_order_fails_closed_with_wrong_references_or_price(engine,bad):
    with Session(engine) as db:
        with db.begin():populate(db)
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(make_order(**bad))
                db.flush()


def test_composite_fk_blocks_cross_tenant_program_cohort(engine):
    with Session(engine) as db:
        with db.begin():populate(db)
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaCohort(
                    id="cohort-B",tenant_id="tenant-B",program_id="program",
                    capacity=1,timezone_name="UTC",
                    registration_opens_at=t0(),registration_closes_at=t0()+timedelta(days=1),
                    starts_at=t0()+timedelta(days=2),ends_at=t0()+timedelta(days=3),status="OPEN",
                ))
                db.flush()


def test_idempotency_and_enrollment_uniqueness(engine):
    with Session(engine) as db:
        with db.begin():
            populate(db)
            db.add(make_order(id="order1",idempotency_key_hash="x"*64))
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(make_order(id="order2",idempotency_key_hash="x"*64))
                db.flush()
        with db.begin():
            db.add(MentoriaEnrollment(id="en1",tenant_id="tenant-A",order_id="order1",
                member_id="member",cohort_id="cohort",status="SUSPENDED"))
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaEnrollment(id="en2",tenant_id="tenant-A",order_id="order1",
                    member_id="member",cohort_id="cohort",status="SUSPENDED"))
                db.flush()


def test_bad_grant_and_cross_tenant_grant_denied(engine):
    with Session(engine) as db:
        with db.begin():
            populate(db)
            db.add(make_order(id="order1"))
            db.flush()
            db.add(MentoriaEnrollment(id="en1",tenant_id="tenant-A",order_id="order1",
                member_id="member",cohort_id="cohort",status="SUSPENDED"))
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaAccessGrant(
                    tenant_id="tenant-B",enrollment_id="en1",status="ACTIVE",
                    starts_at=t0(),expires_at=t0()+timedelta(days=5)))
                db.flush()
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaAccessGrant(
                    tenant_id="tenant-A",enrollment_id="en1",status="ACTIVE",
                    starts_at=t0()+timedelta(days=5),expires_at=t0()))
                db.flush()


def test_payment_event_dedup_and_provider_binding(engine):
    with Session(engine) as db:
        with db.begin():
            populate(db)
            db.add(make_order(id="order1"))
            db.add(MentoriaPaymentAttempt(id="attempt1",tenant_id="tenant-A",order_id="order1",
                provider="asaas",external_reference="external-1",operation_state="NOT_STARTED"))
        with db.begin():
            db.add(MentoriaProviderEvent(id="event1",tenant_id="tenant-A",provider="asaas",
                payment_attempt_id="attempt1",provider_event_id="provider-id",fact_type="UNKNOWN"))
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaProviderEvent(id="event2",tenant_id="tenant-A",provider="asaas",
                    payment_attempt_id="attempt1",provider_event_id="provider-id",fact_type="UNKNOWN"))
                db.flush()
        with pytest.raises(IntegrityError):
            with db.begin():
                db.add(MentoriaProviderEvent(id="event3",tenant_id="tenant-A",provider="other",
                    payment_attempt_id="attempt1",provider_event_id="provider-id-2",fact_type="UNKNOWN"))
                db.flush()


def test_non_postgres_capacity_reservation_stops_before_db_write(engine,monkeypatch):
    monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
    with Session(engine) as db:
        with db.begin():
            populate(db)
        with pytest.raises(MentoriaPersistenceStop,match="POSTGRESQL_ROW_LOCK_REQUIRED"):
            with db.begin():
                reserve_checkout_order(db,identity=VerifiedMentoriaIdentity(
                    tenant_id="tenant-A",issuer="issuer.example",subject="verified-subject",
                ),cohort_id="cohort",offer_id="offer",offer_version=1,
                idempotency_key="very-long-random-key-abcd",request_id="req1",now=t0())
        assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaOrder))==0


def test_disabled_reservation_stops_before_db_write(engine,monkeypatch):
    monkeypatch.setenv("MENTORIA_M2_ENABLED","false")
    with Session(engine) as db:
        with db.begin():populate(db)
        with pytest.raises(MentoriaPersistenceStop,match="M2_FEATURE_DISABLED"):
            with db.begin():
                reserve_checkout_order(db,identity=VerifiedMentoriaIdentity(
                    tenant_id="tenant-A",issuer="issuer.example",subject="verified-subject",
                ),cohort_id="cohort",offer_id="offer",offer_version=1,
                idempotency_key="very-long-random-key-abcd",request_id="req1",now=t0())


def load_migration():
    migration = Path(__file__).resolve().parents[1]/"migrations/versions/018_mentoria_core.py"
    spec=spec_from_file_location("mentoria_018",migration)
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_018_empty_upgrade_and_downgrade():
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    engine=sa.create_engine("sqlite+pysqlite:///:memory:")
    m=load_migration()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)")
        m.op=Operations(MigrationContext.configure(connection))
        m.upgrade()
        assert len([t for t in sa.inspect(connection).get_table_names() if t.startswith("mentoria_")])==12
        m.downgrade()
        assert sa.inspect(connection).get_table_names()==["tenants"]


@pytest.mark.parametrize("table",["mentoria_programs","mentoria_audit_events","mentoria_outbox"])
def test_downgrade_blocks_if_any_data_exists(table):
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    engine=sa.create_engine("sqlite+pysqlite:///:memory:")
    m=load_migration()
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO tenants(id) VALUES ('t')")
        m.op=Operations(MigrationContext.configure(connection))
        m.upgrade()
        if table=="mentoria_programs":
            connection.execute(sa.text(
                "INSERT INTO mentoria_programs (id,tenant_id,slug,title,status,created_at)"
                " VALUES ('p','t','s','title','DRAFT','2026-11-04')"))
        elif table=="mentoria_audit_events":
            connection.execute(sa.text(
                "INSERT INTO mentoria_audit_events (id,tenant_id,actor_type,actor_id,request_id,action,"
                "resource_type,resource_id,metadata_whitelist,occurred_at)"
                " VALUES ('a','t','system','sys','r','NOOP','x','x','{}','2026-11-04')"))
        else:
            connection.execute(sa.text(
                "INSERT INTO mentoria_outbox (id,tenant_id,event_key,event_type,aggregate_id,"
                "payload_whitelist,status,attempt_count,created_at)"
                " VALUES ('o','t','ev','noop','a','{}','PENDING',0,'2026-11-04')"))
        with pytest.raises(RuntimeError,match="STOP_MENTORIA_018_DOWNGRADE_DATA_PRESENT"):
            m.downgrade()
        assert all(sa.inspect(connection).has_table(name) for name in m.M2B_TABLE_NAMES)

def test_migration_018_matches_orm_columns_constraints_and_fks(engine):
    """Prevent DDL drift between frozen Alembic schema and ORM metadata."""
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    fresh=sa.create_engine("sqlite+pysqlite:///:memory:")
    mig=load_migration()
    with fresh.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)")
        mig.op=Operations(MigrationContext.configure(conn))
        mig.upgrade()
        left=sa.inspect(engine)
        right=sa.inspect(conn)
        for model in M2B_TABLES:
            name=model.__table__.name
            model_cols={(c["name"], c["nullable"], c["type"].__class__.__name__)
                        for c in left.get_columns(name)}
            migration_cols={(c["name"], c["nullable"], c["type"].__class__.__name__)
                            for c in right.get_columns(name)}
            assert model_cols == migration_cols,(name,"COLUMNS",model_cols ^ migration_cols)
            def foreignkeys(inspector):
                return {
                    (tuple(f["constrained_columns"]), f["referred_table"],
                     tuple(f["referred_columns"]))
                    for f in inspector.get_foreign_keys(name)
                }
            assert foreignkeys(left)==foreignkeys(right),(name,"FK")
            def checks(inspector):
                return {c["name"] for c in inspector.get_check_constraints(name)}
            assert checks(left)==checks(right),(name,"CHECK")
            def uniques(inspector):
                return {tuple(u["column_names"]) for u in inspector.get_unique_constraints(name)}
            assert uniques(left)==uniques(right),(name,"UNIQUE")
    fresh.dispose()
