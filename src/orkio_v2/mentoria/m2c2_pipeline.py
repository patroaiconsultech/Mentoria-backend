"""Internal-only M2-C2 orchestration: authenticate, read, then transact.

Must be invoked from a dedicated, authenticated provider ingress or worker
implemented later. No route is registered here and nothing calls it at runtime.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from .asaas_reconciliation import AsaasReadOnlyPayments, verify_and_observe
from .financial_ledger import persist_verified_event


def reconcile_delivery(
    *, session_factory: Callable[[], Session], provider: AsaasReadOnlyPayments,
    auth_token_header: str | None, webhook_auth_token: str,
    payload: Mapping[str, Any], request_id: str, now: datetime,
) -> str:
    """No provider I/O inside DB transaction, no caller-supplied tenant."""
    proof = verify_and_observe(
        header_token=auth_token_header,
        configured_token=webhook_auth_token,
        payload=payload,
        provider=provider,
    )
    with session_factory() as db:
        with db.begin():
            return persist_verified_event(db, proof=proof, request_id=request_id, now=now)
