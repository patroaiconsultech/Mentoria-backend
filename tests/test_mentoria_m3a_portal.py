"""M3-A: authenticated, tenant-scoped read-only portal.

SQLite tests prove query and deny decisions only. PostgreSQL and actual
session-cookie integration remain separate release gates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
import sqlalchemy as sa
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orkio_v2.auth import Principal, require_principal
from orkio_v2.database import Base, get_db
from orkio_v2.models import Tenant, User, Membership
from orkio_v2.mentoria.persistence_models import (
    M2B_TABLES, MentoriaAccessGrant, MentoriaCohort,
    MentoriaEnrollment, MentoriaMember, MentoriaOffer,
    MentoriaOrder, MentoriaProgram,
)
from orkio_v2.mentoria.m2c2b_buyer import BuyerIdentityDenied
from orkio_v2.mentoria.portal_read import list_authorized_cohorts
from orkio_v2.mentoria import portal_http

NOW = datetime.now(timezone.utc)


@pytest.fixture
def engine():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def _foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine, tables=[
        Base.metadata.tables["tenants"],
        Base.metadata.tables["users"],
        Base.metadata.tables["memberships"],
        *[m.__table__ for m in M2B_TABLES],
    ])
    try:
        yield engine
    finally:
        engine.dispose()


def seed(db, *, tenant="org-a", user_id="person-a", member="mentor-a",
         financial="PAID", fulfillment="ENROLLED",
         enrollment="ACTIVE", grant="ACTIVE", expires=7,
         member_status="ACTIVE", verified=True):
    db.add(Tenant(id=tenant, name=tenant))
    db.add(User(
        id=user_id, external_subject="oidc-" + user_id,
        email=f"{user_id}@example.test", display_name="Person",
        email_verified_at=NOW if verified else None,
    ))
    db.flush()
    db.add(Membership(id="membership-"+user_id,tenant_id=tenant,user_id=user_id,
                      role="member",active=True))
    db.add(MentoriaProgram(id="program-"+tenant,tenant_id=tenant,slug="ia",
                           title="Mentoria IA para Negócios",status="PUBLISHED"))
    db.flush()
    db.add(MentoriaCohort(
        id="cohort-"+tenant,tenant_id=tenant,program_id="program-"+tenant,
        capacity=50,timezone_name="America/Sao_Paulo",
        registration_opens_at=NOW-timedelta(days=5),
        registration_closes_at=NOW+timedelta(days=1),
        starts_at=NOW+timedelta(days=6),ends_at=NOW+timedelta(days=25),
        status="OPEN",
    ))
    db.add(MentoriaMember(id=member,tenant_id=tenant,issuer="efata-canonical-user",
                          subject=user_id,status=member_status,
                          email_verified_at=NOW if verified else None))
    db.flush()
    db.add(MentoriaOffer(
        tenant_id=tenant,id="offer-"+tenant,version=1,
        program_id="program-"+tenant,cohort_id="cohort-"+tenant,
        amount_cents=149700,currency="BRL",access_days=90,terms_version="v1",
        status="PUBLISHED",
    ))
    db.flush()
    db.add(MentoriaOrder(
        id="order-"+tenant,tenant_id=tenant,member_id=member,
        cohort_id="cohort-"+tenant,offer_id="offer-"+tenant,
        offer_version=1,amount_cents=149700,currency="BRL",
        financial_state=financial,fulfillment_state=fulfillment,
        idempotency_key_hash=("a" if tenant=="org-a" else "b")*64,
        request_fingerprint=("c" if tenant=="org-a" else "d")*64,
    ))
    db.flush()
    db.add(MentoriaEnrollment(
        id="enroll-"+tenant,tenant_id=tenant,member_id=member,
        order_id="order-"+tenant,cohort_id="cohort-"+tenant,
        status=enrollment,
    ))
    db.flush()
    db.add(MentoriaAccessGrant(
        id="grant-"+tenant,tenant_id=tenant,
        enrollment_id="enroll-"+tenant, status=grant,
        starts_at=NOW-timedelta(hours=1),
        expires_at=NOW+timedelta(days=expires),
        revoked_at=None if grant=="ACTIVE" else NOW,
    ))
    db.flush()


def principal(tenant="org-a", user="person-a"):
    return Principal(
        user_id=user,tenant_id=tenant,roles=("member",),
        external_subject="oidc-"+user,email=f"{user}@example.test",
    )


def test_authorized_cohort_only(engine):
    with Session(engine) as db:
        with db.begin():
            seed(db)
        result=list_authorized_cohorts(db,principal=principal(),now=NOW)
        assert len(result)==1
        assert result[0]["program_title"] == "Mentoria IA para Negócios"
        assert "order_id" not in result[0]
        assert "tenant_id" not in result[0]
        assert "member_id" not in result[0]


@pytest.mark.parametrize("financial,fulfillment,enrollment,grant,expires", [
    ("REFUNDED","ENROLLED","ACTIVE","ACTIVE",7),
    ("DISPUTED","ENROLLED","ACTIVE","ACTIVE",7),
    ("REVIEW_REQUIRED","ENROLLED","ACTIVE","ACTIVE",7),
    ("PAID","PAID_UNPLACED","ACTIVE","ACTIVE",7),
    ("PAID","ENROLLED","SUSPENDED","ACTIVE",7),
    ("PAID","ENROLLED","ACTIVE","REVOKED",7),
    ("PAID","ENROLLED","ACTIVE","ACTIVE",0),
])
def test_non_authorized_records_not_returned(engine,financial,fulfillment,enrollment,grant,expires):
    with Session(engine) as db:
        with db.begin():
            seed(db,financial=financial,fulfillment=fulfillment,
                 enrollment=enrollment,grant=grant,expires=expires)
        assert list_authorized_cohorts(db,principal=principal(),now=NOW)==[]


def test_cross_tenant_and_other_user_fail_closed(engine):
    with Session(engine) as db:
        with db.begin():
            seed(db,tenant="org-a",user_id="person-a",member="member-a")
            seed(db,tenant="org-b",user_id="person-b",member="member-b")
        assert len(list_authorized_cohorts(db,principal=principal(),now=NOW))==1
        assert len(list_authorized_cohorts(db,principal=principal("org-b","person-b"),now=NOW))==1
        with pytest.raises(BuyerIdentityDenied):
            list_authorized_cohorts(db,principal=principal("org-b","person-a"),now=NOW)


def test_unverified_buyer_not_authorized(engine):
    with Session(engine) as db:
        with db.begin():seed(db,verified=False)
        with pytest.raises(BuyerIdentityDenied):
            list_authorized_cohorts(db,principal=principal(),now=NOW)


def test_naive_time_rejected(engine):
    with Session(engine) as db:
        with pytest.raises(ValueError, match="PORTAL_TIME_MUST_BE_AWARE"):
            list_authorized_cohorts(db,principal=principal(),now=NOW.replace(tzinfo=None))


def test_http_flag_disabled_and_enabled(engine,monkeypatch):
    # API service test: dependencies are controlled; not a proof of real sessions.
    with Session(engine) as db:
        with db.begin():seed(db)
        app=FastAPI()
        app.include_router(portal_http.router)
        app.dependency_overrides[require_principal]=lambda:principal()
        app.dependency_overrides[get_db]=lambda:db
        monkeypatch.setattr(portal_http,"get_settings",lambda:SimpleNamespace(mentoria_portal_enabled=False))
        client=TestClient(app)
        disabled=client.get("/api/v2/mentoria/portal/me")
        assert disabled.status_code==503
        monkeypatch.setattr(portal_http,"get_settings",lambda:SimpleNamespace(mentoria_portal_enabled=True))
        result=client.get("/api/v2/mentoria/portal/me")
        assert result.status_code==200
        assert len(result.json()["programs"])==1
        assert result.headers["cache-control"]=="private, no-store"
        assert "Cookie" in result.headers["vary"]
