"""Public workshop registration. No platform user, membership or billing grants."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import MentoriaWorkshopRegistration, Tenant

logger = logging.getLogger("orkio.mentoria")
router = APIRouter(prefix="/api/v2/public/mentoria", tags=["mentoria-public"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_VERSION_RE = re.compile(r"^[a-zA-Z0-9._-]{1,40}$")


class WorkshopRegistrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr = Field(max_length=320)
    company_name: str | None = Field(default=None, max_length=160)
    privacy_notice_version: str = Field(min_length=1, max_length=40)
    privacy_accepted: bool = Field(strict=True)
    marketing_opt_in: bool = Field(default=False, strict=True)
    website: str = Field(default="", max_length=200)  # honeypot, must remain blank

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if len(value) < 2 or not any(char.isalpha() for char in value):
            raise ValueError("NAME_INVALID")
        if any(ord(char) < 32 for char in value):
            raise ValueError("NAME_INVALID")
        return value

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, value: str | None) -> str | None:
        if not value:
            return None
        if any(ord(char) < 32 for char in value):
            raise ValueError("COMPANY_INVALID")
        return value


def _configuration():
    settings = get_settings()
    if not settings.mentoria_workshop_enabled:
        raise HTTPException(503, "MENTORIA_WORKSHOP_DISABLED")
    slug = settings.mentoria_workshop_slug.strip()
    tenant_id = settings.mentoria_owner_tenant_id.strip()
    version = settings.mentoria_privacy_notice_version.strip()
    privacy_url = settings.mentoria_privacy_notice_url.strip()
    try:
        url = urlsplit(privacy_url)
        url_valid = (url.scheme == "https" and bool(url.hostname)
                     and not url.username and not url.password)
    except ValueError:
        url_valid = False
    if (not tenant_id or not _SLUG_RE.fullmatch(slug)
        or not _VERSION_RE.fullmatch(version) or not url_valid):
        raise HTTPException(503, "MENTORIA_WORKSHOP_CONFIGURATION_MISSING")
    return tenant_id, slug, version


@router.post("/workshop-registrations", status_code=202)
def create_workshop_registration(
    data: WorkshopRegistrationInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Middleware handles origin, size and rate limits before request validation.
    response.headers["Cache-Control"] = "no-store"
    tenant_id, slug, expected_version = _configuration()
    if not data.privacy_accepted or data.privacy_notice_version != expected_version:
        raise HTTPException(422, "MENTORIA_PRIVACY_ACKNOWLEDGEMENT_REQUIRED")

    # A bot that filled this hidden field receives a generic response but is not stored.
    if data.website:
        return {"status": "received"}

    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(503, "MENTORIA_WORKSHOP_CONFIGURATION_MISSING")

    normalized = str(data.email).strip().lower()
    existing = db.execute(
        select(MentoriaWorkshopRegistration.id).where(
            MentoriaWorkshopRegistration.tenant_id == tenant_id,
            MentoriaWorkshopRegistration.workshop_slug == slug,
            MentoriaWorkshopRegistration.email_normalized == normalized,
        )
    ).first()
    if existing:
        return {"status": "received"}

    record = MentoriaWorkshopRegistration(
        tenant_id=tenant_id,
        workshop_slug=slug,
        full_name=data.full_name,
        email_normalized=normalized,
        company_name=data.company_name,
        privacy_notice_version=expected_version,
        privacy_accepted_at=datetime.now(timezone.utc),
        marketing_opt_in=data.marketing_opt_in,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Unique constraint can race under concurrent signups; the generic result
        # avoids revealing whether an address was already enrolled.
        if db.execute(
            select(MentoriaWorkshopRegistration.id).where(
                MentoriaWorkshopRegistration.tenant_id == tenant_id,
                MentoriaWorkshopRegistration.workshop_slug == slug,
                MentoriaWorkshopRegistration.email_normalized == normalized,
            )
        ).first():
            return {"status": "received"}
        raise HTTPException(503, "MENTORIA_REGISTRATION_UNAVAILABLE")
    except SQLAlchemyError:
        db.rollback()
        logger.warning("mentoria_registration_storage_error request_id=%s",
                         getattr(request.state, "request_id", "unavailable"))
        raise HTTPException(503, "MENTORIA_REGISTRATION_UNAVAILABLE")

    # No email, lead id, tenant id, marketing state or existence is disclosed.
    return {"status": "received"}
