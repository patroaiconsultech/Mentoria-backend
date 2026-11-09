"""M1: public mentoria intake; tests never call an external provider."""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from orkio_v2.config import get_settings
from orkio_v2.database import get_db
from orkio_v2.models import MentoriaWorkshopRegistration, Tenant
from orkio_v2.mentoria.security import _reset_limiter_for_tests


@pytest.fixture(autouse=True)
def mentoria_setup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "mentoria_workshop_enabled", True)
    monkeypatch.setattr(settings, "mentoria_owner_tenant_id", "tenant-1")
    monkeypatch.setattr(settings, "mentoria_workshop_slug", "ia-negocios-workshop")
    monkeypatch.setattr(settings, "mentoria_privacy_notice_version", "2026-11")
    monkeypatch.setattr(settings, "mentoria_privacy_notice_url",
                        "https://example.org/privacidade")
    _reset_limiter_for_tests()
    yield
    _reset_limiter_for_tests()


def payload(**overrides):
    data = {
        "full_name": "Cliente Exemplo",
        "email": "CLIENTE@example.com",
        "company_name": "Empresa Demo",
        "privacy_notice_version": "2026-11",
        "privacy_accepted": True,
        "marketing_opt_in": False,
        "website": "",
    }
    return {**data, **overrides}


def rows(client):
    # Fixture client provides a tenant-1; query via the same override DB.
    from orkio_v2.main import app
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        return list(db.scalars(
            select(MentoriaWorkshopRegistration).order_by(
                MentoriaWorkshopRegistration.tenant_id
            )
        ))
    finally:
        gen.close()


def test_feature_flag_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mentoria_workshop_enabled", False)
    result = client.post("/api/v2/public/mentoria/workshop-registrations", json=payload())
    assert result.status_code == 503
    assert result.json()["detail"] == "MENTORIA_WORKSHOP_DISABLED"


def test_registration_saved_server_tenant_with_privacy_and_no_pii_response(client):
    result = client.post("/api/v2/public/mentoria/workshop-registrations", json=payload())
    assert result.status_code == 202
    assert result.json() == {"status": "received"}
    assert result.headers["cache-control"] == "no-store"
    saved = [row for row in rows(client) if row.email_normalized == "cliente@example.com"]
    assert len(saved) == 1
    assert saved[0].tenant_id == "tenant-1"
    assert saved[0].privacy_notice_version == "2026-11"
    assert saved[0].marketing_opt_in is False
    assert saved[0].privacy_accepted_at is not None


def test_repeat_email_normalized_is_idempotent(client):
    first = client.post("/api/v2/public/mentoria/workshop-registrations",
                        json=payload(email="DUPLICADO@EXAMPLE.NET"))
    second = client.post("/api/v2/public/mentoria/workshop-registrations",
                         json=payload(email="duplicado@example.net", marketing_opt_in=True))
    assert (first.status_code, second.status_code) == (202, 202)
    saved = [row for row in rows(client) if row.email_normalized == "duplicado@example.net"]
    assert len(saved) == 1
    assert saved[0].marketing_opt_in is False  # duplicate does not silently change consent


@pytest.mark.parametrize("overrides", [
    {"privacy_accepted": False},
    {"privacy_accepted": "yes"},
    {"privacy_notice_version": "outdated"},
    {"full_name": "A"},
    {"email": "not-an-email"},
    {"marketing_opt_in": "invalid"},
])
def test_invalid_inputs_never_create_registration(client, overrides):
    result = client.post("/api/v2/public/mentoria/workshop-registrations",
                         json=payload(**{"email": "invalid-test@example.net", **overrides}))
    assert result.status_code == 422
    assert not [row for row in rows(client)
                if row.email_normalized == "invalid-test@example.net"]


def test_honeypot_returns_generic_without_storing(client):
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(email="bot@example.net", website="filled by bot"))
    assert r.status_code == 202
    assert r.json() == {"status": "received"}
    assert not [row for row in rows(client) if row.email_normalized == "bot@example.net"]


def test_server_configuration_absent_fails_closed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mentoria_owner_tenant_id", "")
    result = client.post("/api/v2/public/mentoria/workshop-registrations", json=payload())
    assert result.status_code == 503


def test_owner_tenant_is_server_selected_not_client(client, monkeypatch):
    from orkio_v2.main import app
    from orkio_v2.database import get_db
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    if db.get(Tenant, "tenant-m1-other") is None:
        db.add(Tenant(id="tenant-m1-other", name="Mentoria Outro"))
        db.commit()
    gen.close()
    monkeypatch.setattr(get_settings(), "mentoria_owner_tenant_id", "tenant-m1-other")
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(email="other@example.net"))
    assert r.status_code == 202
    stored = [row for row in rows(client) if row.email_normalized == "other@example.net"]
    assert len(stored) == 1 and stored[0].tenant_id == "tenant-m1-other"
    spoof = client.post("/api/v2/public/mentoria/workshop-registrations",
                        json=payload(email="other2@example.net", tenant_id="tenant-1"))
    assert spoof.status_code == 422


def test_ip_rate_limit_is_enforced(client):
    for n in range(5):
        r = client.post("/api/v2/public/mentoria/workshop-registrations",
                        json=payload(email=f"ratelimit{n}@example.net"))
        assert r.status_code == 202
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(email="ratelimit5@example.net"))
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_rejects_wrong_content_type(client):
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    content="hello", headers={"content-type": "text/plain"})
    assert r.status_code == 415


def test_origin_is_required_in_staging_and_redis_fail_closed(client, monkeypatch):
    from orkio_v2.mentoria import security
    from orkio_v2.services.activation_rate_limit import RedisRateLimitUnavailable

    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "mentoria_rate_limit_secret", "x" * 40)

    r = client.post("/api/v2/public/mentoria/workshop-registrations", json=payload())
    assert r.status_code == 403
    assert r.json()["detail"] == "MENTORIA_ORIGIN_INVALID"

    async def offline(**_kwargs):
        raise RedisRateLimitUnavailable("simulated")
    monkeypatch.setattr(security, "check_external_activation_rate_limit", offline)
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    headers={"Origin": "http://localhost:5173"}, json=payload())
    assert r.status_code == 503
    assert r.json()["detail"] == "MENTORIA_RATE_LIMIT_UNAVAILABLE"


def test_large_body_is_rejected(client):
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(full_name="A" * 5000))
    assert r.status_code == 413



def test_invalid_config_url_fails_without_crashing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mentoria_privacy_notice_url", "https://[broken")
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(email="bad-config@example.net"))
    assert r.status_code == 503


def test_registration_rejects_unknown_tenant(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mentoria_owner_tenant_id", "tenant-not-in-database")
    r = client.post("/api/v2/public/mentoria/workshop-registrations",
                    json=payload(email="unknown-owner@example.net"))
    assert r.status_code == 503
