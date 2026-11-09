"""Read-only authenticated buyer identity adapter, separate from billing.

Requires canonical session/OIDC principal + active platform membership and
a pre-provisioned MentoriaMember bound to immutable canonical user ID.
Never creates a member, order, enrollment, grant or tenant.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal
from ..models import Membership, User
from .persistence_models import MentoriaMember
from .transactional_repository import VerifiedMentoriaIdentity

CANONICAL_MEMBER_ISSUER = "efata-canonical-user"


class BuyerIdentityDenied(ValueError):
    pass


def verified_buyer(db: Session, principal: Principal) -> VerifiedMentoriaIdentity:
    if not isinstance(principal, Principal) or not principal.tenant_id or not principal.user_id:
        raise BuyerIdentityDenied("AUTHENTICATED_BUYER_REQUIRED")
    user = db.get(User, principal.user_id)
    if (
        user is None
        or user.external_subject != principal.external_subject
        or user.email_verified_at is None
    ):
        raise BuyerIdentityDenied("BUYER_IDENTITY_UNVERIFIED")

    membership = db.scalar(select(Membership).where(
        Membership.user_id == user.id,
        Membership.tenant_id == principal.tenant_id,
        Membership.active.is_(True),
    ))
    if (
        membership is None or membership.tenant_id != principal.tenant_id
        or membership.user_id != user.id or not membership.active
    ):
        raise BuyerIdentityDenied("BUYER_MEMBERSHIP_REQUIRED")
    member = db.scalar(select(MentoriaMember).where(
        MentoriaMember.tenant_id == principal.tenant_id,
        MentoriaMember.issuer == CANONICAL_MEMBER_ISSUER,
        MentoriaMember.subject == user.id,
        MentoriaMember.status == "ACTIVE",
        MentoriaMember.email_verified_at.is_not(None),
    ))
    if (
        member is None or member.tenant_id != principal.tenant_id
        or member.issuer != CANONICAL_MEMBER_ISSUER or member.subject != user.id
        or member.status != "ACTIVE" or member.email_verified_at is None
    ):
        raise BuyerIdentityDenied("MENTORIA_MEMBER_NOT_LINKED")
    return VerifiedMentoriaIdentity(
        tenant_id=principal.tenant_id,
        issuer=CANONICAL_MEMBER_ISSUER,
        subject=user.id,
    )
