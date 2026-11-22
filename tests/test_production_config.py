"""
Tests for Phase 5.1 Production Configuration, WSGI Entry Point, and Security Boundaries.

Verifies:
- Fail-closed environment selection (unknown or unsupported environments rejected).
- Production SECRET_KEY validation.
- WSGI entry point restricted to production.
- WSGI module import isolation (zero database initialization at import time).
- Explicit CLI 'init-db' command execution and database effects.
- Single-hop ProxyFix header rewriting (x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0).
- Forwarded host and port rejection (preventing host-header injection).
- Request-size boundary enforcement (MAX_CONTENT_LENGTH = 1 MB yielding HTTP 413).
- Backward compatibility of development and testing configurations.
"""

import os
import sys
import tempfile
import importlib
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from app import create_app
from config import Config, DevelopmentConfig, TestingConfig, ProductionConfig


# --- 1. Environment Selection & Fail-Closed Tests ---

def test_unknown_environment_fails_closed():
    """Verifies that unknown or misspelled environment names fail closed with ValueError."""
    with pytest.raises(ValueError) as exc_info:
        create_app("unknown_env")
    assert "CRITICAL CONFIGURATION ERROR: Unknown environment 'unknown_env'" in str(exc_info.value)
    assert "Valid configurations" in str(exc_info.value)


def test_unsupported_environments_rejected():
    """Verifies that unsupported environments like 'staging' or 'prod' fail closed."""
    for bad_env in ["staging", "prod", "dev", "test"]:
        with pytest.raises(ValueError):
            create_app(bad_env)


def test_default_environment_resolution(monkeypatch):
    """Verifies that SEVAPATH_ENV is read when config_name is None, defaulting to 'default'."""
    monkeypatch.delenv("SEVAPATH_ENV", raising=False)
    app = create_app(None)
    assert app.config["DEBUG"] is True

    monkeypatch.setenv("SEVAPATH_ENV", "testing")
    app_test = create_app(None)
    assert app_test.config["TESTING"] is True


# --- 2. Production Secret Enforcement Tests ---

def test_production_missing_secret_key_fails(monkeypatch):
    """Verifies that production requires an explicit SECRET_KEY in the environment."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        create_app("production")
    assert "Production requires a secure SECRET_KEY" in str(exc_info.value)


def test_production_insecure_default_secret_key_fails(monkeypatch):
    """Verifies that production rejects the hardcoded development fallback SECRET_KEY."""
    monkeypatch.setenv("SECRET_KEY", "sevapath-dev-insecure-secret-key-2026")
    with pytest.raises(RuntimeError) as exc_info:
        create_app("production")
    assert "Application refused to start with missing or default development key" in str(exc_info.value)


def test_production_valid_configuration(monkeypatch):
    """Verifies that valid production configuration sets all required security keys."""
    monkeypatch.setenv("SECRET_KEY", "valid-production-secret-key-xyz-1234567890")
    app = create_app("production")
    assert app.config["DEBUG"] is False
    assert app.config["TESTING"] is False
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024
    assert app.config["PROXY_FIX_ENABLED"] is True
    assert app.config["PROXY_FIX_HOPS"] == 1


# --- 3. WSGI Entry Point & Import Isolation Tests ---

def test_wsgi_production_guard(monkeypatch):
    """Verifies that wsgi.py strictly refuses to load under non-production environments."""
    monkeypatch.setenv("SEVAPATH_ENV", "development")
    if "wsgi" in sys.modules:
        del sys.modules["wsgi"]

    with pytest.raises(RuntimeError) as exc_info:
        import wsgi
    assert "wsgi.py is strictly restricted to production" in str(exc_info.value)


def test_wsgi_import_does_not_call_init_db(monkeypatch):
    """
    CRITICAL TEST: Verifies that importing wsgi.py executes zero database initialization.
    Database migrations and seeding must remain an explicit release step.
    """
    monkeypatch.setenv("SEVAPATH_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "valid-production-secret-for-wsgi-import-test")

    with patch("app.models.database.init_db") as mock_db_init, \
         patch("app.init_db") as mock_app_init:

        if "wsgi" in sys.modules:
            del sys.modules["wsgi"]

        import wsgi

        # Assert wsgi.app exists and is a valid Flask app
        assert isinstance(wsgi.app, Flask)
        assert wsgi.app.config["DEBUG"] is False

        # Assert neither reference to init_db was called during module import
        assert mock_db_init.called is False
        assert mock_app_init.called is False


# --- 4. Explicit CLI 'init-db' Invocation Tests ---

def test_cli_init_db_invokes_initialization(tmp_path):
    """
    Verifies that running 'flask init-db' explicitly executes database initialization
    and seeds initial services with return code 0.
    """
    temp_db = str(tmp_path / "cli_init_test.sqlite")
    app = create_app("testing")
    app.config["DATABASE_PATH"] = temp_db

    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])

    assert result.exit_code == 0
    assert "Initialized SQLite database and seeded initial services successfully." in result.output

    # Verify that database was physically initialized
    import sqlite3
    conn = sqlite3.connect(temp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "services" in tables
    assert "requirements" in tables
    assert "schema_migrations" in tables
    conn.close()


# --- 5. Single-Hop ProxyFix Trust Boundaries Tests ---

def test_single_hop_proxyfix_trust_boundaries(monkeypatch):
    """
    Verifies that ProxyFix rewrites client IP and TLS scheme for 1 trusted proxy hop,
    while strictly ignoring forwarded host and port headers.
    """
    monkeypatch.setenv("SECRET_KEY", "proxy-test-secret-key-1234567890")
    app = create_app("production")

    @app.route("/test-proxy-endpoint")
    def test_proxy():
        from flask import request
        return {
            "remote_addr": request.remote_addr,
            "is_secure": request.is_secure,
            "host": request.host,
            "scheme": request.scheme,
        }

    client = app.test_client()

    headers = {
        "X-Forwarded-For": "203.0.113.195",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "attacker-spoofed-host.com",
        "X-Forwarded-Port": "9999",
    }

    res = client.get("/test-proxy-endpoint", headers=headers)
    assert res.status_code == 200
    data = res.json

    # Trusted single-hop rewrites
    assert data["remote_addr"] == "203.0.113.195"
    assert data["is_secure"] is True
    assert data["scheme"] == "https"

    # Untrusted headers rejected (x_host=0, x_port=0)
    assert data["host"] != "attacker-spoofed-host.com"
    assert "9999" not in data["host"]


def test_proxyfix_disabled_in_development():
    """Verifies that development configuration ignores forwarded proxy headers."""
    app = create_app("development")

    @app.route("/test-dev-proxy")
    def test_dev():
        from flask import request
        return {
            "remote_addr": request.remote_addr,
            "is_secure": request.is_secure,
        }

    client = app.test_client()
    headers = {
        "X-Forwarded-For": "203.0.113.195",
        "X-Forwarded-Proto": "https",
    }

    res = client.get("/test-dev-proxy", headers=headers)
    assert res.status_code == 200
    data = res.json

    # In development, forwarded headers are not trusted
    assert data["remote_addr"] != "203.0.113.195"
    assert data["is_secure"] is False


def test_proxyfix_invalid_hops_rejected(monkeypatch):
    """Verifies that non-single-hop configurations fail closed in Phase 5.1."""
    monkeypatch.setenv("SECRET_KEY", "hops-test-secret-key-1234567890")
    monkeypatch.setenv("PROXY_FIX_HOPS", "2")
    with pytest.raises(ValueError) as exc_info:
        create_app("production")
    assert "Phase 5.1 strictly enforces a single trusted proxy hop" in str(exc_info.value)


# --- 6. Request-Size Limit (MAX_CONTENT_LENGTH) Tests ---

def test_request_size_under_limit_accepted(client):
    """Verifies that JSON requests under the 1 MB limit are processed normally."""
    payload = {"field_type": "phone", "value": "9876543210", "lang": "en"}
    res = client.post("/api/validate-format", json=payload)
    assert res.status_code == 200


def test_request_size_over_limit_rejected():
    """Verifies that payloads exceeding 1 MB return HTTP 413 Payload Too Large."""
    app = create_app("testing")

    @app.route("/test-upload", methods=["POST"])
    def test_upload():
        from flask import request
        return {"bytes_received": len(request.data)}

    client = app.test_client()

    # 1.2 MB oversized payload (exceeds MAX_CONTENT_LENGTH of 1,048,576 bytes)
    oversized_data = b"x" * (1024 * 1024 + 200 * 1024)

    res = client.post(
        "/test-upload",
        data=oversized_data,
        content_type="application/octet-stream"
    )
    assert res.status_code == 413


# --- 7. Development and Testing Config Invariance Tests ---

def test_development_config_defaults():
    """Verifies that DevelopmentConfig maintains expected developer defaults."""
    app = create_app("development")
    assert app.config["DEBUG"] is True
    assert app.config["TESTING"] is False
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024
    assert app.config["PROXY_FIX_ENABLED"] is False


def test_testing_config_defaults():
    """Verifies that TestingConfig maintains test isolation."""
    app = create_app("testing")
    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert "test" in app.config["DATABASE_PATH"]
    assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024
    assert app.config["PROXY_FIX_ENABLED"] is False
