"""Independent public M1-AI boundary. No storage and no commercial writes."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from .assistant import (
    ALLOWED_MODELS, CATALOG_VERSION, authorized_reply, provider_reply,
)

router = APIRouter(prefix="/api/v2/public/mentoria", tags=["mentoria-assistant"])
_INFLIGHT = asyncio.Semaphore(3)
_QUESTION_RE = re.compile(r"[^\s]")
# Per-process admission control. A timed-out response does not imply that
# the blocking provider worker has stopped; the slot belongs to the worker.
_PROVIDER_TIMEOUT_SECONDS = 15.0
_ADMISSION_TIMEOUT_SECONDS = 0.3


def _provider_finished(task: asyncio.Task[str]) -> None:
    """Release admission only once the blocking provider call has ended.

    A late provider failure must also be observed, without logging its
    potentially sensitive exception body.
    """
    _INFLIGHT.release()
    if not task.cancelled():
        try:
            task.result()
        except Exception:
            pass



class AssistantQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=3, max_length=500)
    ai_processing_acknowledged: bool = Field(strict=True)
    no_sensitive_data_acknowledged: bool = Field(strict=True)


@router.post("/assistant")
async def ask_mentoria_assistant(data: AssistantQuestion, response: Response):
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    if not settings.mentoria_assistant_enabled:
        raise HTTPException(503, "MENTORIA_ASSISTANT_DISABLED")
    try:
        privacy = urlsplit(settings.mentoria_privacy_notice_url)
        privacy_ready = (privacy.scheme == "https" and bool(privacy.hostname)
                         and not privacy.username and not privacy.password)
    except ValueError:
        privacy_ready = False
    if (
        not settings.mentoria_owner_tenant_id.strip()
        or not privacy_ready
        or settings.mentoria_assistant_catalog_version != CATALOG_VERSION
    ):
        raise HTTPException(503, "MENTORIA_ASSISTANT_CONFIGURATION_MISSING")
    if not data.ai_processing_acknowledged or not data.no_sensitive_data_acknowledged:
        raise HTTPException(422, "MENTORIA_ASSISTANT_ACKNOWLEDGEMENT_REQUIRED")
    if not _QUESTION_RE.search(data.message) or any(
        ord(char) < 32 and char not in "\t\n" for char in data.message
    ):
        raise HTTPException(422, "MENTORIA_ASSISTANT_QUESTION_INVALID")

    # Public business facts and sensitive-input refusals never leave this host.
    approved = authorized_reply(data.message)
    if approved is not None:
        return {"reply": approved, "source": "catalog", "catalog_version": CATALOG_VERSION}

    # Provider-only configuration must not disable approved local answers.
    if (
        settings.mentoria_assistant_model not in ALLOWED_MODELS
        or not (settings.openai_api_key or "").strip()
    ):
        raise HTTPException(503, "MENTORIA_ASSISTANT_CONFIGURATION_MISSING")

    # Admission slots follow the *worker*, not the HTTP timeout. asyncio's
    # cancellation of to_thread cannot stop a blocking network call.
    try:
        await asyncio.wait_for(_INFLIGHT.acquire(), timeout=_ADMISSION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(503, "MENTORIA_ASSISTANT_UNAVAILABLE") from None
    try:
        worker = asyncio.create_task(
            asyncio.to_thread(provider_reply, data.message, settings)
        )
        worker.add_done_callback(_provider_finished)
    except BaseException:
        _INFLIGHT.release()
        raise

    try:
        answer = await asyncio.wait_for(
            asyncio.shield(worker), timeout=_PROVIDER_TIMEOUT_SECONDS
        )
    except (asyncio.TimeoutError, RuntimeError):
        raise HTTPException(503, "MENTORIA_ASSISTANT_UNAVAILABLE") from None
    return {"reply": answer, "source": "ai", "catalog_version": CATALOG_VERSION}
