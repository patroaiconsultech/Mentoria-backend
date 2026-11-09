"""M2-B PostgreSQL concurrent seat lock test, OFF by default.

Requires a dedicated disposable database named *_m2b_test and:
 MENTORIA_M2B_ALLOW_SCHEMA_TEST=true
 MENTORIA_M2B_TEST_DATABASE_URL=postgresql+psycopg://.../dedicated_m2b_test
Never run against application/production databases.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Barrier
from uuid import uuid4
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.engine.url import make_url

from orkio_v2.database import Base
from orkio_v2.models import Tenant
from orkio_v2.mentoria.persistence_models import (
    M2B_TABLES, MentoriaProgram, MentoriaCohort, MentoriaOffer, MentoriaMember,
    MentoriaOrder, MentoriaSeatHold, MentoriaAuditEvent, MentoriaOutbox,
)
from orkio_v2.mentoria.transactional_repository import (
    MentoriaPersistenceStop, VerifiedMentoriaIdentity, reserve_checkout_order,
)


@pytest.fixture()
def isolated_postgres(monkeypatch):
    url = os.environ.get("MENTORIA_M2B_TEST_DATABASE_URL")
    if not url or os.environ.get("MENTORIA_M2B_ALLOW_SCHEMA_TEST") != "true":
        pytest.skip("No explicit disposable PG M2B test configuration")
    parsed = make_url(url)
    if not parsed.get_backend_name().startswith("postgresql") or not (
        parsed.database and parsed.database.endswith("_m2b_test")
    ):
        pytest.fail("Refusing non-disposable / non-PostgreSQL M2B test URL")
    # Test DB schema is isolated and disposable; never drop objects in public.
    engine = sa.create_engine(url, pool_size=4, max_overflow=2)
    schema = "m2b_" + uuid4().hex[:16]  # validated identifier alphabet
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            Base.metadata.create_all(conn, tables=[
                Base.metadata.tables["tenants"], *[m.__table__ for m in M2B_TABLES],
            ])
        monkeypatch.setenv("MENTORIA_M2_ENABLED","true")
        yield engine, schema
    finally:
        # Explicit test-only gate; schema contains only test objects.
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def seed(engine, schema, now):
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            db.add(Tenant(id="tenant-test",name="Test tenant"))
            db.flush()
            db.add(MentoriaProgram(id="prog",tenant_id="tenant-test",slug="prog",title="Mentoria",
                                    status="PUBLISHED"))
            db.flush()
            db.add(MentoriaCohort(
                id="cohort",tenant_id="tenant-test",program_id="prog",capacity=1,timezone_name="UTC",
                registration_opens_at=now-timedelta(days=1),
                registration_closes_at=now+timedelta(days=1),
                starts_at=now+timedelta(days=2),ends_at=now+timedelta(days=4),status="OPEN",
            ))
            db.flush()
            db.add(MentoriaOffer(
                tenant_id="tenant-test",id="offer",version=1,cohort_id="cohort",program_id="prog",
                amount_cents=149700,currency="BRL",access_days=90,terms_version="v1",status="PUBLISHED",
            ))
            db.add_all([
                MentoriaMember(id=f"member-{n}",tenant_id="tenant-test",issuer="trusted",
                               subject=f"subject-{n}",status="ACTIVE")
                for n in (1,2)
            ])


def test_last_seat_competing_orders_yield_only_one(isolated_postgres):
    engine,schema=isolated_postgres
    now=datetime.now(timezone.utc).replace(microsecond=0)
    seed(engine,schema,now)
    sync=Barrier(2)
    def attempt(n):
        with Session(engine) as db:
            sync.wait(timeout=8)
            try:
                with db.begin():
                    db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                    result=reserve_checkout_order(
                        db,identity=VerifiedMentoriaIdentity("tenant-test","trusted",f"subject-{n}"),
                        cohort_id="cohort",offer_id="offer",offer_version=1,
                        idempotency_key=f"my-unique-random-key-{n}-123456",
                        request_id=f"req-{n}",now=now,
                    )
                    return result.id
            except MentoriaPersistenceStop as error:
                return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1=pool.submit(attempt,1); f2=pool.submit(attempt,2)
        results=[f1.result(timeout=20),f2.result(timeout=20)]
    assert results.count("COHORT_FULL")==1,results
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaOrder))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaSeatHold))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaAuditEvent))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaOutbox))==1


def test_idempotent_retry_does_not_duplicate_order(isolated_postgres):
    engine,schema=isolated_postgres
    now=datetime.now(timezone.utc).replace(microsecond=0)
    seed(engine,schema,now)
    args=dict(
        identity=VerifiedMentoriaIdentity("tenant-test","trusted","subject-1"),
        cohort_id="cohort",offer_id="offer",offer_version=1,
        idempotency_key="retry-safe-order-key-123456789",request_id="req-repeat",now=now,
    )
    for iteration in (0,1):
        with Session(engine) as db:
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                order=reserve_checkout_order(db,**args)
                if iteration==0:first_id=order.id
                else:assert order.id==first_id
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaOrder))==1
            assert db.scalar(sa.select(sa.func.count()).select_from(MentoriaSeatHold))==1


# M2-B PG qualification extensions (proposal-only).
# These tests run ONLY through the disposable PostgreSQL fixture above.

def _counts(engine, schema):
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            return tuple(
                db.scalar(sa.select(sa.func.count()).select_from(model))
                for model in (MentoriaOrder, MentoriaSeatHold, MentoriaAuditEvent, MentoriaOutbox)
            )


def test_same_key_concurrent_retries_return_one_order(isolated_postgres):
    """A retry racing its first request must neither duplicate nor consume a second seat."""
    engine, schema = isolated_postgres
    now = datetime.now(timezone.utc).replace(microsecond=0)
    seed(engine, schema, now)
    barrier = Barrier(2)
    idem = "same-retry-key-123456789"
    def attempt(index):
        with Session(engine) as db:
            barrier.wait(timeout=8)
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                order = reserve_checkout_order(
                    db, identity=VerifiedMentoriaIdentity(
                        "tenant-test", "trusted", "subject-1"),
                    cohort_id="cohort", offer_id="offer", offer_version=1,
                    idempotency_key=idem, request_id=f"retry-{index}", now=now,
                )
                return order.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(attempt, 1), pool.submit(attempt, 2)
        ids = (a.result(timeout=20), b.result(timeout=20))
    assert ids[0] == ids[1]
    assert _counts(engine, schema) == (1, 1, 1, 1)


def test_rolled_back_reservation_leaves_no_partial_rows(isolated_postgres):
    """Failure after flush must undo order, hold, audit and outbox as one unit."""
    engine, schema = isolated_postgres
    now = datetime.now(timezone.utc).replace(microsecond=0)
    seed(engine, schema, now)
    payload = dict(
        identity=VerifiedMentoriaIdentity("tenant-test", "trusted", "subject-1"),
        cohort_id="cohort", offer_id="offer", offer_version=1,
        idempotency_key="rollback-safe-key-123456789", request_id="rollback-test", now=now,
    )
    with pytest.raises(RuntimeError, match="SYNTHETIC_AFTER_FLUSH"):
        with Session(engine) as db:
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                reserve_checkout_order(db, **payload)
                raise RuntimeError("SYNTHETIC_AFTER_FLUSH")
    assert _counts(engine, schema) == (0, 0, 0, 0)
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            assert reserve_checkout_order(db, **payload).id
    assert _counts(engine, schema) == (1, 1, 1, 1)


def test_cross_tenant_subject_cannot_reserve_foreign_cohort(isolated_postgres):
    """A real member in tenant B cannot use tenant A's cohort or offer."""
    engine, schema = isolated_postgres
    now = datetime.now(timezone.utc).replace(microsecond=0)
    seed(engine, schema, now)
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
            db.add(Tenant(id="tenant-other", name="Other tenant"))
            db.flush()
            db.add(MentoriaMember(
                id="member-other", tenant_id="tenant-other",
                issuer="trusted", subject="subject-1", status="ACTIVE"))
    with Session(engine) as db:
        with pytest.raises(MentoriaPersistenceStop, match="COHORT_UNAVAILABLE"):
            with db.begin():
                db.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                reserve_checkout_order(
                    db, identity=VerifiedMentoriaIdentity(
                        "tenant-other", "trusted", "subject-1"),
                    cohort_id="cohort", offer_id="offer", offer_version=1,
                    idempotency_key="other-tenant-key-1234567",
                    request_id="cross-tenant", now=now,
                )
    assert _counts(engine, schema) == (0, 0, 0, 0)


def test_migration_017_018_pg_upgrade_downgrade_empty(isolated_postgres):
    """Real PostgreSQL DDL on a new schema, NOT a full historical 001->016 rehearsal."""
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    engine, _ = isolated_postgres
    schema = "mtmig_" + uuid4().hex[:16]
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    def load(file, name):
        spec = spec_from_file_location(name, versions / file)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    m17 = load("017_mentoria_workshop.py", "mtpg_017")
    m18 = load("018_mentoria_core.py", "mtpg_018")
    assert m17.down_revision == "016_thread_participant_access_expiry"
    assert m18.down_revision == m17.revision

    with engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(sa.text("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)"))
            migrations_op = Operations(MigrationContext.configure(conn))
            m17.op = migrations_op
            m18.op = migrations_op
            m17.upgrade()
            m18.upgrade()
            table_names = set(sa.inspect(conn).get_table_names(schema=schema))
            assert table_names >= {
                "tenants", "mentoria_workshop_registrations",
                *(model.__table__.name for model in M2B_TABLES),
            }
            fks = sa.inspect(conn).get_foreign_keys(
                "mentoria_orders", schema=schema
            )
            assert {"fk_mt_order_member", "fk_mt_order_offer"} <= {
                fk["name"] for fk in fks
            }
            m18.downgrade()
            m17.downgrade()
            assert sa.inspect(conn).get_table_names(schema=schema) == ["tenants"]
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def test_migration_018_pg_downgrade_blocked_if_populated(isolated_postgres):
    """Never drop an M2-B table containing operational data."""
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    engine, _ = isolated_postgres
    schema = "mtguard_" + uuid4().hex[:16]
    migration = Path(__file__).resolve().parents[1] / "migrations/versions/018_mentoria_core.py"
    spec = spec_from_file_location("mt_pg_downgrade_guard", migration)
    m18 = module_from_spec(spec)
    spec.loader.exec_module(m18)
    with engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(sa.text("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)"))
            m18.op = Operations(MigrationContext.configure(conn))
            m18.upgrade()
            conn.execute(sa.text("INSERT INTO tenants(id) VALUES ('test-owner')"))
            conn.execute(sa.text("""
                INSERT INTO mentoria_programs
                    (id,tenant_id,slug,title,status,created_at)
                VALUES ('program','test-owner','slug','Title','DRAFT',CURRENT_TIMESTAMP)
            """))
            with pytest.raises(RuntimeError, match="STOP_MENTORIA_018_DOWNGRADE_DATA_PRESENT"):
                m18.downgrade()
            assert sa.inspect(conn).has_table("mentoria_programs", schema=schema)
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
