"""M2-C2B inbound interfaces, disabled unless separately configured.

Webhook: POST trusted provider receipt -> durable DB commit -> 200.
Buyer: GET validated session and pre-provisioned MentoriaMember; read only.
No payment, checkout, enrollment or grants are created here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..auth import Principal, require_principal
from ..config import get_settings
from ..database import get_db, SessionLocal
from .asaas_reconciliation import (
    authenticate_notification, FinancialProofRejected, AuthenticatedNotification,
)
from .m2c2b_buyer import BuyerIdentityDenied, verified_buyer
from .m2c2b_ingress import WebhookIngressStopped, record_authenticated_delivery, ingress_enabled

WEBHOOK_PATH = "/api/v2/mentoria/webhooks/asaas"
MAX_WEBHOOK_BODY_BYTES = 32768
router = APIRouter(tags=["mentoria-private"])


def _persist_receipt(notification: AuthenticatedNotification) -> None:
    with SessionLocal() as db:
        with db.begin():
            record_authenticated_delivery(db, notification=notification,
                                          now=datetime.now(timezone.utc))


async def _bounded_json(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "MENTORIA_JSON_REQUIRED")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise HTTPException(400, "MENTORIA_LENGTH_INVALID") from None
        if size < 0 or size > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(413, "MENTORIA_REQUEST_TOO_LARGE")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(413, "MENTORIA_REQUEST_TOO_LARGE")
        body.extend(chunk)
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "MENTORIA_JSON_INVALID") from None


@router.post(WEBHOOK_PATH, include_in_schema=False)
async def asaas_webhook(request: Request):
    settings = get_settings()
    if not settings.mentoria_m2c2b_enabled or not ingress_enabled():
        raise HTTPException(503, "MENTORIA_INGRESS_DISABLED")
    payload = await _bounded_json(request)
    try:
        notification = authenticate_notification(
            header_token=request.headers.get("asaas-access-token"),
            configured_token=settings.mentoria_asaas_webhook_token,
            payload=payload,
        )
    except FinancialProofRejected as exc:
        code = str(exc)
        if code == "WEBHOOK_NOT_CONFIGURED":
            raise HTTPException(503, "MENTORIA_WEBHOOK_NOT_CONFIGURED") from None
        if code == "WEBHOOK_UNAUTHENTICATED":
            raise HTTPException(401, "MENTORIA_WEBHOOK_UNAUTHENTICATED") from None
        raise HTTPException(400, "MENTORIA_WEBHOOK_INVALID") from None
    try:
        # Blocking PostgreSQL I/O offloaded from event loop. Must finish/commit
        # before 200; never fire-and-forget.
        await run_in_threadpool(_persist_receipt, notification)
    except WebhookIngressStopped as exc:
        if str(exc) == "CONTRADICTORY_REPLAY":
            raise HTTPException(409, "MENTORIA_EVENT_CONFLICT") from None
        raise HTTPException(503, "MENTORIA_RECEIPT_UNAVAILABLE") from None
    except SQLAlchemyError:
        raise HTTPException(503, "MENTORIA_RECEIPT_UNAVAILABLE") from None
    return JSONResponse({"received": True}, status_code=200,
                        headers={"Cache-Control": "no-store"})


@router.get("/api/v2/mentoria/buyer/me", include_in_schema=False)
def current_mentoria_buyer(
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.mentoria_m2c2b_enabled:
        raise HTTPException(503, "MENTORIA_BUYER_DISABLED")
    try:
        verified_buyer(db, principal)
    except BuyerIdentityDenied:
        raise HTTPException(403, "MENTORIA_BUYER_NOT_VERIFIED") from None
    # No tenant, membership, PII, order or grant disclosure in this gate.
    return JSONResponse({"status": "ready"},
                        headers={"Cache-Control": "no-store"})
