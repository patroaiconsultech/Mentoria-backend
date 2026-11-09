"""M3-A restricted mentor portal: never a payment or access-grant endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..auth import Principal, require_principal
from ..config import get_settings
from ..database import get_db
from .m2c2b_buyer import BuyerIdentityDenied
from .portal_read import list_authorized_cohorts

router = APIRouter(tags=["mentoria-portal"])


@router.get("/api/v2/mentoria/portal/me", include_in_schema=False)
def mentoria_portal_me(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
):
    if not get_settings().mentoria_portal_enabled:
        raise HTTPException(503, "MENTORIA_PORTAL_DISABLED")
    try:
        programs = list_authorized_cohorts(
            db, principal=principal, now=datetime.now(timezone.utc)
        )
    except BuyerIdentityDenied:
        raise HTTPException(403, "MENTORIA_PORTAL_NOT_AUTHORIZED") from None
    return JSONResponse(
        {"programs": programs},
        headers={"Cache-Control": "private, no-store", "Vary": "Cookie, Authorization"},
    )
