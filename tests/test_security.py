"""
Pytest security, privacy, and defensive hardening test suite for SevaPath.

Tests:
- Production SECRET_KEY enforcement (fail-safe without import-time crashes)
- Strict exclusive X-CSRF-Token header enforcement (JSON body fallback rejection)
- Cache-Control: no-store on CSRF token endpoint
- Defensive JSON parsing (rejection of arrays, strings, numbers, null, malformed JSON)
- Strict language validation (only 'en' and 'ta' accepted)
- Caplog privacy test confirming submitted phone/email values never appear in application logs
- Session ownership validation under CSRF
- Zero persistence on format validation endpoint
"""

import os
import pytest
from app import create_app
from app.models.database import get_db
from config import ProductionConfig, DevelopmentConfig, TestingConfig


# --- Production SECRET_KEY Tests ---

def test_production_config_importable_without_exception():
    """
    CRITICAL CORRECTION 1:
    Merely importing ProductionConfig must not raise an exception.
    """
    assert ProductionConfig is not None
    assert ProductionConfig.DEBUG is False
    assert ProductionConfig.SESSION_COOKIE_SECURE is True


def test_production_secret_key_enforcement(monkeypatch):
    """
    CRITICAL CORRECTION 1:
    ProductionConfig must require a real SECRET_KEY from the environment at app creation time.
    Fails safely with a clear configuration error if missing or using insecure default.
    """
    # 1. Ensure SECRET_KEY is not in environment
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        create_app("production")
    assert "Production requires a secure SECRET_KEY" in str(exc_info.value)

    # 2. When SECRET_KEY is legitimately provided, creation succeeds
    monkeypatch.setenv("SECRET_KEY", "real-secure-production-secret-key-xyz-987654321")
    prod_app = create_app("production")
    assert prod_app is not None
    assert prod_app.config["SECRET_KEY"] == "real-secure-production-secret-key-xyz-987654321"


# --- Strict CSRF Header Tests ---

def test_csrf_token_endpoint_cache_control(client):
    """
    CRITICAL CORRECTION 5:
    CSRF token response must include Cache-Control: no-store.
    """
    res = client.get("/api/csrf-token")
    assert res.status_code == 200
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert res.headers.get("Pragma") == "no-cache"


def test_csrf_body_token_without_header_rejected(client):
    """
    CRITICAL CORRECTION 2:
    Prove that a valid token in the JSON body without the X-CSRF-Token header is rejected with 403.
    """
    init_res = client.get("/api/service/income-certificate/state")
    valid_csrf_token = init_res.get_json()["csrf_token"]

    # Send valid CSRF token in the JSON body, but OMIT the X-CSRF-Token header
    res = client.post(
        "/api/service/income-certificate/toggle",
        json={
            "requirement_code": "applicant_photo",
            "is_completed": True,
            "csrf_token": valid_csrf_token  # In body only
        }
    )
    assert res.status_code == 403
    assert "Requires valid 'X-CSRF-Token' header" in res.get_json()["error"]


def test_csrf_missing_and_forged_header_rejected(client):
    """Verifies that missing, empty, or forged X-CSRF-Token headers receive HTTP 403."""
    client.get("/api/service/income-certificate/state")

    # 1. Missing header
    res_missing = client.post(
        "/api/service/income-certificate/toggle",
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert res_missing.status_code == 403

    # 2. Forged header
    res_forged = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": "forged_invalid_hex_token_00000000000000000000000000000000000000"},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert res_forged.status_code == 403


# --- Defensive JSON Parsing & Language Validation Tests ---

@pytest.mark.parametrize("invalid_payload", [
    [1, 2, 3],                  # Array (list)
    "raw string payload",       # String
    12345,                      # Number
    True,                       # Boolean
])
def test_defensive_json_non_dict_rejected(client, invalid_payload):
    """
    CRITICAL CORRECTION 4:
    Return HTTP 400 for arrays, strings, numbers, boolean, and non-dict JSON bodies.
    """
    # 1. Test on /api/validate-format
    res_val = client.post("/api/validate-format", json=invalid_payload)
    assert res_val.status_code == 400
    assert "must be a JSON object" in res_val.get_json()["error"]

    # 2. Test on /api/service/<slug>/toggle
    init_res = client.get("/api/service/income-certificate/state")
    csrf_token = init_res.get_json()["csrf_token"]

    res_toggle = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json=invalid_payload
    )
    assert res_toggle.status_code == 400
    assert "must be a JSON object" in res_toggle.get_json()["error"]

    # 3. Test on /api/service/<slug>/reset
    res_reset = client.post(
        "/api/service/income-certificate/reset",
        headers={"X-CSRF-Token": csrf_token},
        json=invalid_payload
    )
    assert res_reset.status_code == 400
    assert "must be a JSON object" in res_reset.get_json()["error"]


def test_strict_language_validation(client):
    """
    CRITICAL CORRECTION 4:
    Accept only 'en' and 'ta'. Return HTTP 400 on unsupported language codes.
    """
    # Unsupported language
    res_unsupported = client.post("/api/validate-format", json={
        "field_type": "phone",
        "value": "9876543210",
        "lang": "fr"
    })
    assert res_unsupported.status_code == 400
    assert "Invalid language code" in res_unsupported.get_json()["error"]

    # Supported languages
    res_en = client.post("/api/validate-format", json={
        "field_type": "phone",
        "value": "9876543210",
        "lang": "en"
    })
    assert res_en.status_code == 200

    res_ta = client.post("/api/validate-format", json={
        "field_type": "phone",
        "value": "9876543210",
        "lang": "ta"
    })
    assert res_ta.status_code == 200


# --- Privacy, Logging & Persistence Tests ---

def test_privacy_no_logging_of_sensitive_data(client, caplog):
    """
    CRITICAL CORRECTION 5:
    Caplog test confirming submitted phone and email values do not appear in application logs.
    """
    sensitive_phone = "9876543210"
    sensitive_email = "citizen_secret_personal@domain.org"

    with caplog.at_level("DEBUG"):
        client.post("/api/validate-format", json={"field_type": "phone", "value": sensitive_phone})
        client.post("/api/validate-format", json={"field_type": "email", "value": sensitive_email})
        client.post("/api/validate-format", json={"field_type": "phone", "value": "invalid_phone_secret"})

    # Assert neither sensitive inputs appear in captured logs
    assert sensitive_phone not in caplog.text
    assert sensitive_email not in caplog.text
    assert "invalid_phone_secret" not in caplog.text


def test_api_validate_format_privacy_zero_persistence(client, app):
    """
    CRITICAL PRIVACY REQUIREMENT:
    The format validation endpoint must NOT write to any SQLite database table.
    """
    with app.app_context():
        db = get_db()
        before_sessions = db.execute("SELECT COUNT(*) FROM preparation_sessions").fetchone()[0]
        before_items = db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0]

    client.post("/api/validate-format", json={"field_type": "phone", "value": "9876543210"})
    client.post("/api/validate-format", json={"field_type": "email", "value": "citizen@test.com"})

    with app.app_context():
        db = get_db()
        after_sessions = db.execute("SELECT COUNT(*) FROM preparation_sessions").fetchone()[0]
        after_items = db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0]

    assert before_sessions == after_sessions
    assert before_items == after_items


def test_session_ownership_preserved_with_valid_csrf(client):
    """
    CSRF does not replace session ownership checks. A valid CSRF token cannot be used
    to mutate another service's requirements or invalid requirement codes.
    """
    income_res = client.get("/api/service/income-certificate/state")
    csrf_token = income_res.get_json()["csrf_token"]

    # Attempt to toggle a requirement code on community certificate that belongs to income
    cross_res = client.post(
        "/api/service/community-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "requirement_code": "family_smart_card",
            "is_completed": True
        }
    )
    assert cross_res.status_code == 400
    assert "not found for this service" in cross_res.get_json()["error"]
