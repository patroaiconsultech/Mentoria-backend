"""Fail-closed public intake boundary: exact route, origin, body, distributed limits.

Public endpoint is stateless and requires no session cookie; it is specifically
exempted from the platform CSRF-cookie mechanism, not from origin enforcement.
"""
from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import get_settings
from ..public_activation_security import (
    InMemorySlidingWindowRateLimiter,
    _buffer_bounded_body,
    _replay_receive,
    resolve_client_ip,
)
from ..services.activation_rate_limit import (
    RedisRateLimitUnavailable,
    check_external_activation_rate_limit,
)

PUBLIC_REGISTRATION_PATH = "/api/v2/public/mentoria/workshop-registrations"
PUBLIC_ASSISTANT_PATH = "/api/v2/public/mentoria/assistant"
MAX_BODY_BYTES = 4096
_memory_limiter = InMemorySlidingWindowRateLimiter()


def _reset_limiter_for_tests():
    _memory_limiter.reset()


async def _reject(scope: Scope, send: Send, status: int, detail: str, retry_after: int = 0):
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if retry_after > 0:
        headers["Retry-After"] = str(retry_after)
    response = JSONResponse({"detail": detail}, status_code=status, headers=headers)
    async def disconnected():
        return {"type": "http.disconnect"}
    await response(scope, disconnected, send)


class MentoriaPublicSecurityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http" or scope.get("path") not in {PUBLIC_REGISTRATION_PATH, PUBLIC_ASSISTANT_PATH}:
            await self.app(scope, receive, send)
            return

        if scope.get("method", "").upper() == "OPTIONS":
            # CORS preflight is handled by outer CORSMiddleware.
            await self.app(scope, receive, send)
            return
        if scope.get("method", "").upper() != "POST":
            await _reject(scope, send, 405, "MENTORIA_METHOD_NOT_ALLOWED")
            return

        settings = get_settings()
        is_assistant = scope.get("path") == PUBLIC_ASSISTANT_PATH
        if is_assistant and not settings.mentoria_assistant_enabled:
            await _reject(scope, send, 503, "MENTORIA_ASSISTANT_DISABLED")
            return
        if not is_assistant and not settings.mentoria_workshop_enabled:
            await _reject(scope, send, 503, "MENTORIA_WORKSHOP_DISABLED")
            return
        max_body_bytes = 2048 if is_assistant else MAX_BODY_BYTES
        rate_class = "mentoria_assistant" if is_assistant else "mentoria_workshop"
        per_ip_limit = 6 if is_assistant else 5

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        origin = headers.get("origin", "")
        allowed = {item.strip() for item in settings.allowed_origins.split(",") if item.strip()}
        if (origin and origin not in allowed) or (
            settings.environment in {"staging", "production"} and not origin
        ):
            await _reject(scope, send, 403, "MENTORIA_ORIGIN_INVALID")
            return
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            await _reject(scope, send, 415, "MENTORIA_JSON_REQUIRED")
            return

        length_str = headers.get("content-length")
        if length_str is not None:
            try:
                length = int(length_str)
                if length < 0:
                    raise ValueError
            except ValueError:
                await _reject(scope, send, 400, "MENTORIA_CONTENT_LENGTH_INVALID")
                return
            if length > max_body_bytes:
                await _reject(scope, send, 413, "MENTORIA_REQUEST_TOO_LARGE")
                return

        client_ip = resolve_client_ip(scope, settings)
        if settings.environment in {"development", "test"}:
            decision = _memory_limiter.check(
                f"{rate_class}:{client_ip}",
                limit=per_ip_limit, window_seconds=600,
            )
        else:
            if len(settings.mentoria_rate_limit_secret) < 32:
                await _reject(scope, send, 503, "MENTORIA_RATE_LIMIT_UNAVAILABLE")
                return
            try:
                decision = await check_external_activation_rate_limit(
                    endpoint_class=rate_class,
                    client_ip=client_ip,
                    token=None,
                    secret=settings.mentoria_rate_limit_secret,
                    limit=per_ip_limit,
                    window_seconds=600,
                )
            except RedisRateLimitUnavailable:
                await _reject(scope, send, 503, "MENTORIA_RATE_LIMIT_UNAVAILABLE")
                return

        if not decision.allowed:
            await _reject(scope, send, 429, "MENTORIA_RATE_LIMITED",
                          retry_after=decision.retry_after_seconds)
            return

        # A second global budget protects against many IP addresses consuming
        # unlimited provider calls. This is distributed in staging/production.
        if is_assistant:
            if settings.environment in {"development", "test"}:
                daily = _memory_limiter.check(
                    "mentoria_assistant:global", limit=200, window_seconds=86400
                )
            else:
                try:
                    daily = await check_external_activation_rate_limit(
                        endpoint_class="mentoria_assistant_daily",
                        client_ip="global",
                        token=None,
                        secret=settings.mentoria_rate_limit_secret,
                        limit=200,
                        window_seconds=86400,
                    )
                except RedisRateLimitUnavailable:
                    await _reject(scope, send, 503, "MENTORIA_RATE_LIMIT_UNAVAILABLE")
                    return
            if not daily.allowed:
                await _reject(scope, send, 429, "MENTORIA_RATE_LIMITED",
                              retry_after=daily.retry_after_seconds)
                return

        messages, _, oversized = await _buffer_bounded_body(receive, max_body_bytes)
        if oversized:
            await _reject(scope, send, 413, "MENTORIA_REQUEST_TOO_LARGE")
            return
        await self.app(scope, _replay_receive(messages), send)
