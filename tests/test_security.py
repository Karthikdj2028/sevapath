"""
Pytest security and privacy test suite for SevaPath.

Tests:
- Session cookie flags (HttpOnly, SameSite, Secure)
- Cryptographic CSRF token generation and validation
- Strict rejection of missing, malformed, and forged CSRF tokens (HTTP 403)
- Session ownership validation under CSRF
- Format validation API endpoint privacy (no database persistence, no sensitive echoing)
"""

from app.models.database import get_db
from config import ProductionConfig, DevelopmentConfig, TestingConfig


def test_session_cookie_configuration(app):
    """Verifies OWASP-aligned session cookie settings in app config."""
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_production_cookie_security():
    """Verifies ProductionConfig mandates HTTPS-only cookies."""
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == "Lax"


def test_csrf_token_endpoint(client):
    """Verifies that GET /api/csrf-token returns a valid 64-hex-char token."""
    res = client.get("/api/csrf-token")
    assert res.status_code == 200
    data = res.get_json()
    assert "csrf_token" in data
    token = data["csrf_token"]
    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes hex encoded


def test_csrf_missing_token_rejected_on_toggle(client):
    """Verifies POST /api/service/income-certificate/toggle without CSRF receives HTTP 403."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]

    res = client.post(
        "/api/service/income-certificate/toggle",
        json={
            "session_token": session_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )
    assert res.status_code == 403
    assert "CSRF token missing or invalid" in res.get_json()["error"]


def test_csrf_missing_token_rejected_on_reset(client):
    """Verifies POST /api/service/income-certificate/reset without CSRF receives HTTP 403."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]

    res = client.post(
        "/api/service/income-certificate/reset",
        json={"session_token": session_token}
    )
    assert res.status_code == 403
    assert "CSRF token missing or invalid" in res.get_json()["error"]


def test_csrf_forged_token_rejected(client):
    """Verifies that an arbitrary / forged CSRF token is rejected with HTTP 403."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]

    forged_token = "0" * 64
    res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": forged_token},
        json={
            "session_token": session_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )
    assert res.status_code == 403
    assert "CSRF token missing or invalid" in res.get_json()["error"]


def test_csrf_malformed_token_rejected(client):
    """Verifies that empty string or whitespace token receives HTTP 403."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]

    res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": ""},
        json={
            "session_token": session_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )
    assert res.status_code == 403


def test_session_ownership_preserved_with_valid_csrf(client):
    """
    CRITICAL REQUIREMENT:
    CSRF does not replace session ownership checks. A valid CSRF token cannot be used
    to mutate another service's session.
    """
    # 1. Create a session for income-certificate
    income_res = client.get("/api/service/income-certificate/state")
    income_sess_token = income_res.get_json()["session_token"]
    csrf_token = income_res.get_json()["csrf_token"]

    # 2. Try to use income session token on community-certificate endpoint
    cross_res = client.post(
        "/api/service/community-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "session_token": income_sess_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )
    assert cross_res.status_code == 403
    assert "Unauthorized or mismatched session token" in cross_res.get_json()["error"]


# --- Format Validation Privacy Tests ---

def test_api_validate_format_phone(client):
    """Verifies POST /api/validate-format for phone returns normalized value."""
    res = client.post("/api/validate-format", json={
        "field_type": "phone",
        "value": "+91 98765 43210",
        "lang": "en"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["is_valid"] is True
    assert data["cleaned_value"] == "9876543210"
    assert "disclaimer" in data


def test_api_validate_format_email(client):
    """Verifies POST /api/validate-format for email returns normalized lowercased value."""
    res = client.post("/api/validate-format", json={
        "field_type": "email",
        "value": "Citizen.TN@TamilNadu.gov.in",
        "lang": "en"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["is_valid"] is True
    assert data["cleaned_value"] == "citizen.tn@tamilnadu.gov.in"


def test_api_validate_format_deferred_government_identifier(client):
    """Verifies that government identifiers are safely rejected with deferred notice."""
    res = client.post("/api/validate-format", json={
        "field_type": "can_number",
        "value": "1234567890123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["is_valid"] is False
    assert "deferred" in data["error_message"].lower()


def test_api_validate_format_privacy_zero_persistence(client, app):
    """
    CRITICAL PRIVACY REQUIREMENT:
    The format validation endpoint must NOT write to any SQLite database table.
    """
    with app.app_context():
        db = get_db()
        before_sessions = db.execute("SELECT COUNT(*) FROM preparation_sessions").fetchone()[0]
        before_items = db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0]

    # Validate phone and email
    client.post("/api/validate-format", json={"field_type": "phone", "value": "9876543210"})
    client.post("/api/validate-format", json={"field_type": "email", "value": "citizen@test.com"})

    with app.app_context():
        db = get_db()
        after_sessions = db.execute("SELECT COUNT(*) FROM preparation_sessions").fetchone()[0]
        after_items = db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0]

    assert before_sessions == after_sessions
    assert before_items == after_items


def test_api_validate_format_error_no_sensitive_echo(client):
    """
    CRITICAL PRIVACY REQUIREMENT:
    Error responses must not unnecessarily echo the submitted sensitive input.
    """
    sensitive_input = "9876543210_SECRET_LEAK"
    res = client.post("/api/validate-format", json={
        "field_type": "phone",
        "value": sensitive_input
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["is_valid"] is False
    assert sensitive_input not in data["error_message"]
