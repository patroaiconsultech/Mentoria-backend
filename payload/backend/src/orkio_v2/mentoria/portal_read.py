"""M3-A: read-only, fail-closed listing of a buyer's active mentorship access.

No order creation, financial state mutation, member bootstrap, grants,
recordings or class resources. Authorization is evaluated against current DB
facts on every request; no browser-selected tenant or buyer identity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..auth import Principal
from .domain_contracts import (
    AccessSnapshot, EnrollmentStatus, FinancialState, GrantStatus,
    allows_mentoria_access,
)
from .m2c2b_buyer import verified_buyer
from .persistence_models import (
    MentoriaAccessGrant, MentoriaCohort, MentoriaEnrollment,
    MentoriaMember, MentoriaOrder, MentoriaProgram,
)

MAX_PORTAL_COHORTS = 50


def _require_utc_now(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("PORTAL_TIME_MUST_BE_AWARE")
    return now.astimezone(timezone.utc)


def list_authorized_cohorts(
    db: Session, *, principal: Principal, now: datetime
) -> list[dict]:
    """Filter in SQL by canonical tenant/buyer, then check the domain ACL.

    The SQL filter and predicate are deliberately redundant: stale, refunded,
    suspended and revoked grants must never enter the response.
    """
    now = _require_utc_now(now)
    buyer = verified_buyer(db, principal)
    tenant_id = buyer.tenant_id
    member = db.scalar(select(MentoriaMember).where(
        MentoriaMember.tenant_id == tenant_id,
        MentoriaMember.issuer == buyer.issuer,
        MentoriaMember.subject == buyer.subject,
        MentoriaMember.status == "ACTIVE",
        MentoriaMember.email_verified_at.is_not(None),
    ))
    if member is None:
        return []

    rows = db.execute(
        select(MentoriaEnrollment, MentoriaAccessGrant,
               MentoriaOrder, MentoriaCohort, MentoriaProgram)
        .join(
            MentoriaAccessGrant,
            and_(
                MentoriaAccessGrant.tenant_id == MentoriaEnrollment.tenant_id,
                MentoriaAccessGrant.enrollment_id == MentoriaEnrollment.id,
            ),
        )
        .join(
            MentoriaOrder,
            and_(
                MentoriaOrder.tenant_id == MentoriaEnrollment.tenant_id,
                MentoriaOrder.id == MentoriaEnrollment.order_id,
                MentoriaOrder.member_id == MentoriaEnrollment.member_id,
                MentoriaOrder.cohort_id == MentoriaEnrollment.cohort_id,
            ),
        )
        .join(
            MentoriaCohort,
            and_(
                MentoriaCohort.tenant_id == MentoriaEnrollment.tenant_id,
                MentoriaCohort.id == MentoriaEnrollment.cohort_id,
            ),
        )
        .join(
            MentoriaProgram,
            and_(
                MentoriaProgram.tenant_id == MentoriaCohort.tenant_id,
                MentoriaProgram.id == MentoriaCohort.program_id,
            ),
        )
        .where(
            MentoriaEnrollment.tenant_id == tenant_id,
            MentoriaEnrollment.member_id == member.id,
            MentoriaEnrollment.status == "ACTIVE",
            MentoriaOrder.financial_state == "PAID",
            MentoriaOrder.fulfillment_state == "ENROLLED",
            MentoriaAccessGrant.status == "ACTIVE",
            MentoriaAccessGrant.revoked_at.is_(None),
            MentoriaAccessGrant.starts_at <= now,
            MentoriaAccessGrant.expires_at > now,
            MentoriaCohort.status.in_(("OPEN", "CLOSED", "IN_PROGRESS", "COMPLETED")),
        )
        .order_by(MentoriaCohort.starts_at.desc(), MentoriaCohort.id)
        .limit(MAX_PORTAL_COHORTS)
    ).all()

    visible: list[dict] = []
    for enrollment, grant, order, cohort, program in rows:
        # The query is not a grant: inspect current states independently.
        snapshot = AccessSnapshot(
            tenant_id=enrollment.tenant_id,
            buyer_subject_id=buyer.subject,
            cohort_id=cohort.id,
            financial_state=FinancialState(order.financial_state),
            enrollment_status=EnrollmentStatus(enrollment.status),
            grant_status=GrantStatus(grant.status),
            grant_starts_at=grant.starts_at,
            grant_expires_at=grant.expires_at,
            revoked_at=grant.revoked_at,
        )
        # SQLite can strip tzinfo in tests; normalize stored instants only
        # after confirming the database dialect and making UTC assumption explicit.
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            def assume_sqlite_utc(value: datetime) -> datetime:
                return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            snapshot = AccessSnapshot(
                tenant_id=snapshot.tenant_id,
                buyer_subject_id=snapshot.buyer_subject_id,
                cohort_id=snapshot.cohort_id,
                financial_state=snapshot.financial_state,
                enrollment_status=snapshot.enrollment_status,
                grant_status=snapshot.grant_status,
                grant_starts_at=assume_sqlite_utc(grant.starts_at),
                grant_expires_at=assume_sqlite_utc(grant.expires_at),
                revoked_at=assume_sqlite_utc(grant.revoked_at) if grant.revoked_at else None,
            )
        if not allows_mentoria_access(
            principal_subject_id=buyer.subject,
            owner_tenant_id=tenant_id,
            requested_cohort_id=cohort.id,
            snapshot=snapshot,
            now=now,
        ):
            continue
        visible.append({
            "cohort_id": cohort.id,
            "program_title": program.title,
            "starts_at": cohort.starts_at.isoformat(),
            "ends_at": cohort.ends_at.isoformat(),
            "timezone_name": cohort.timezone_name,
            "access_expires_at": grant.expires_at.isoformat(),
        })
    return visible
