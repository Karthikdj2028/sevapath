"""
Tests for Phase 5.2 Deployment Contracts, Database PRAGMAs, and Release Verification.

Verifies:
- Connection-level PRAGMA configuration (foreign_keys=ON, busy_timeout=5000, synchronous=NORMAL).
- Database initialization WAL mode (journal_mode=WAL).
- HTTP liveness check (/health) and readiness check (/health?check=ready).
- Backward compatibility of database migrations on a disposable legacy database.
- Concurrent writes serialization under busy_timeout=5000.
- Systemd service file and Nginx reverse-proxy configuration contracts.
- Release and rollback script contracts (code-only rollback, safe snapshot paths).
- Deployment verification diagnostic tool functions.
"""

import os
import sys
import uuid
import tempfile
import sqlite3
import threading
import pytest
from flask import Flask

from app import create_app
from app.models.database import get_db, init_db_connection, init_db, run_migrations
from deployment.scripts.verify_deployment import (
    check_scratch_write,
    check_lock_diagnostic,
    check_snapshot_integrity
)


# --- 1. SQLite Connection PRAGMAs & WAL Mode Tests ---

def test_get_db_connection_pragmas(tmp_path):
    """Verifies get_db() applies foreign_keys=ON, busy_timeout=5000, and synchronous=NORMAL."""
    db_file = str(tmp_path / "test_pragmas.sqlite")
    app = create_app("testing")
    app.config["DATABASE_PATH"] = db_file

    with app.app_context():
        db = get_db()
        fk = db.execute("PRAGMA foreign_keys;").fetchone()[0]
        timeout = db.execute("PRAGMA busy_timeout;").fetchone()[0]
        sync = db.execute("PRAGMA synchronous;").fetchone()[0]

        assert fk == 1, "foreign_keys must be enabled (1)"
        assert timeout == 5000, "busy_timeout must be 5000ms"
        assert sync == 1, "synchronous must be NORMAL (1)"


def test_init_db_connection_pragmas(tmp_path):
    """Verifies init_db_connection applies foreign_keys=ON, busy_timeout=5000, and synchronous=NORMAL."""
    db_file = str(tmp_path / "test_init_conn.sqlite")
    conn = init_db_connection(db_file)
    try:
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        sync = conn.execute("PRAGMA synchronous;").fetchone()[0]

        assert fk == 1, "foreign_keys must be enabled (1)"
        assert timeout == 5000, "busy_timeout must be 5000ms"
        assert sync == 1, "synchronous must be NORMAL (1)"
    finally:
        conn.close()


def test_init_db_sets_wal_mode(tmp_path):
    """Verifies init_db initializes the database with journal_mode=WAL."""
    db_file = str(tmp_path / "test_wal_init.sqlite")
    app = create_app("testing")
    app.config["DATABASE_PATH"] = db_file

    with app.app_context():
        init_db(app)
        db = get_db()
        journal_mode = db.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal", f"journal_mode must be WAL, got {journal_mode}"


# --- 2. Health Liveness & Readiness Tests ---

def test_health_liveness_check(client):
    """Verifies GET /health returns 200 without database access."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json
    assert data["status"] == "healthy"
    assert data["service"] == "SevaPath"
    assert "database" in data


def test_health_readiness_check_success(client):
    """Verifies GET /health?check=ready returns 200 when database responds."""
    res = client.get("/health?check=ready")
    assert res.status_code == 200
    data = res.json
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_health_readiness_check_failure():
    """Verifies GET /health?check=ready returns 503 when database is unavailable."""
    app = create_app("testing")
    # Point to an unwritable, invalid database directory
    app.config["DATABASE_PATH"] = "/dev/null/invalid/path/db.sqlite"

    client = app.test_client()
    res = client.get("/health?check=ready")
    assert res.status_code == 503
    data = res.json
    assert data["status"] == "unavailable"
    assert data["database"] == "error"


# --- 3. Migration Backward Compatibility on Disposable Legacy Database ---

def test_migration_backward_compatibility_on_disposable_db(tmp_path):
    """
    Verifies that running migrations on a disposable legacy database:
    - Retains historical citizen session records and session items.
    - Successfully applies new schema migrations with BEGIN IMMEDIATE.
    - Preserves foreign key integrity.
    - Remains fully queryable by application functions.
    """
    legacy_db = str(tmp_path / "disposable_legacy.sqlite")
    conn = sqlite3.connect(legacy_db)
    cur = conn.cursor()

    # 1. Simulate legacy Phase 3 schema (before citizen_sessions migration)
    cur.execute("""
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE preparation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            current_state_bitmask INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (service_id) REFERENCES services(id)
        );
    """)
    cur.execute("""
        CREATE TABLE requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            requirement_code TEXT NOT NULL,
            is_mandatory INTEGER DEFAULT 1,
            document_type TEXT NOT NULL,
            order_seq INTEGER DEFAULT 0,
            FOREIGN KEY (service_id) REFERENCES services(id)
        );
    """)
    cur.execute("""
        CREATE TABLE session_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            requirement_id INTEGER NOT NULL,
            is_completed INTEGER DEFAULT 0,
            completed_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (session_id) REFERENCES preparation_sessions(id)
        );
    """)

    # Insert representative historical records
    cur.execute("INSERT INTO services (slug, department) VALUES ('test-service', 'Revenue');")
    cur.execute("INSERT INTO preparation_sessions (service_id, session_token) VALUES (1, 'legacy_tok_123');")
    cur.execute("INSERT INTO requirements (service_id, requirement_code, document_type) VALUES (1, 'doc_1', 'pdf');")
    cur.execute("INSERT INTO session_items (session_id, requirement_id, is_completed) VALUES (1, 1, 1);")
    conn.commit()

    # 2. Execute migrations using SevaPath's run_migrations
    run_migrations(conn)

    # 3. Verify integrity
    integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
    fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
    assert integrity == "ok"
    assert len(fk_violations) == 0

    # 4. Verify historical data remains intact
    hist_sess = cur.execute("SELECT session_token FROM preparation_sessions WHERE id = 1;").fetchone()[0]
    assert hist_sess == "legacy_tok_123"

    hist_item = cur.execute("SELECT is_completed, applicability FROM session_items WHERE id = 1;").fetchone()
    assert hist_item[0] == 1
    assert hist_item[1] == "undetermined"  # Default value populated by migration

    # 5. Verify schema_migrations recorded version 1
    versions = {r[0] for r in cur.execute("SELECT version FROM schema_migrations;").fetchall()}
    assert 1 in versions

    conn.close()


# --- 4. Concurrent Writes Serialization Test ---

def test_concurrent_writes_busy_timeout(tmp_path):
    """
    Verifies that multi-threaded concurrent writers do not raise 'database is locked'
    under PRAGMA busy_timeout=5000.
    """
    db_file = str(tmp_path / "concurrent_test.sqlite")
    conn = init_db_connection(db_file)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, val INTEGER);")
    conn.execute("INSERT INTO counter VALUES (1, 0);")
    conn.commit()
    conn.close()

    errors = []

    def writer_task(worker_id):
        try:
            worker_conn = init_db_connection(db_file)
            for _ in range(5):
                cur = worker_conn.cursor()
                cur.execute("BEGIN IMMEDIATE;")
                curr = cur.execute("SELECT val FROM counter WHERE id = 1;").fetchone()[0]
                cur.execute("UPDATE counter SET val = ? WHERE id = 1;", (curr + 1,))
                worker_conn.commit()
            worker_conn.close()
        except Exception as e:
            errors.append(f"Worker {worker_id} error: {e}")

    threads = [threading.Thread(target=writer_task, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent write errors encountered: {errors}"

    verify_conn = init_db_connection(db_file)
    final_val = verify_conn.execute("SELECT val FROM counter WHERE id = 1;").fetchone()[0]
    verify_conn.close()
    assert final_val == 25, f"Expected final counter val 25, got {final_val}"


# --- 5. Deployment Diagnostic Utility Tests ---

def test_verify_deployment_scratch_write(tmp_path):
    """Verifies check_scratch_write creates and deletes a probe file in instance dir."""
    instance_dir = str(tmp_path / "instance")
    os.makedirs(instance_dir, exist_ok=True)

    success = check_scratch_write(instance_dir)
    assert success is True
    # Confirm probe file was unlinked
    files = os.listdir(instance_dir)
    assert not any(f.startswith(".probe_") for f in files)


def test_verify_deployment_lock_diagnostic(tmp_path):
    """Verifies check_lock_diagnostic performs non-mutating BEGIN IMMEDIATE / ROLLBACK."""
    db_file = str(tmp_path / "diag_test.sqlite")
    conn = init_db_connection(db_file)
    conn.execute("CREATE TABLE t (x INT);")
    conn.commit()
    conn.close()

    success = check_lock_diagnostic(db_file)
    assert success is True


def test_verify_deployment_snapshot_integrity(tmp_path):
    """Verifies check_snapshot_integrity validates a good SQLite snapshot and rejects corrupted files."""
    db_file = str(tmp_path / "good_snap.sqlite")
    conn = init_db_connection(db_file)
    conn.execute("CREATE TABLE t (x INT);")
    conn.commit()
    conn.close()

    assert check_snapshot_integrity(db_file) is True

    bad_file = str(tmp_path / "bad_snap.sqlite")
    with open(bad_file, "wb") as f:
        f.write(b"NOT_A_SQLITE_DATABASE_CORRUPTED_BYTES")
    assert check_snapshot_integrity(bad_file) is False


# --- 6. Configuration & Script Contract Tests ---

def test_systemd_service_file_contract():
    """Verifies deployment/systemd/sevapath.service directives."""
    service_path = os.path.join(os.path.dirname(__file__), "..", "deployment", "systemd", "sevapath.service")
    assert os.path.isfile(service_path), "sevapath.service must exist"

    with open(service_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Type=exec" in content, "Service must use Type=exec"
    assert "User=sevapath" in content, "Service must run as unprivileged user sevapath"
    assert "Group=sevapath" in content
    assert "WorkingDirectory=/opt/sevapath/current" in content
    assert "EnvironmentFile=/etc/sevapath/production.env" in content
    assert "ExecStart=/opt/sevapath/venv/bin/gunicorn --config /opt/sevapath/current/gunicorn.conf.py wsgi:app" in content
    assert "ReadWritePaths=/opt/sevapath/shared/instance" in content
    assert "PrivateTmp=true" in content
    assert "ProtectSystem=strict" in content


def test_nginx_conf_file_contract():
    """Verifies deployment/nginx/sevapath.conf directives."""
    conf_path = os.path.join(os.path.dirname(__file__), "..", "deployment", "nginx", "sevapath.conf")
    assert os.path.isfile(conf_path), "sevapath.conf must exist"

    with open(conf_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "upstream sevapath_gunicorn" in content
    assert "server 127.0.0.1:8000" in content
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in content
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in content
    assert 'proxy_set_header X-Forwarded-Host "";' in content
    assert "client_max_body_size 1M;" in content
    assert "add_header Cache-Control \"public, max-age=86400, must-revalidate\";" in content
    assert "__SEVAPATH_DOMAIN__" in content
    assert "__SSL_CERT_PATH__" in content


def test_release_script_contract():
    """Verifies deployment/scripts/release.sh fail-closed and safety directives."""
    script_path = os.path.join(os.path.dirname(__file__), "..", "deployment", "scripts", "release.sh")
    assert os.path.isfile(script_path), "release.sh must exist"

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "set -euo pipefail" in content
    assert "VACUUM INTO" in content
    assert "pre_deploy_" in content
    assert "PRAGMA integrity_check" in content
    assert "systemctl restart sevapath" in content
    assert "health?check=ready" in content
    # Verify no fragile grep | cut secret extraction
    assert "grep -i secret" not in content.lower()


def test_rollback_script_contract():
    """Verifies deployment/scripts/rollback.sh is code-only and never modifies database."""
    script_path = os.path.join(os.path.dirname(__file__), "..", "deployment", "scripts", "rollback.sh")
    assert os.path.isfile(script_path), "rollback.sh must exist"

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "set -euo pipefail" in content
    assert "systemctl restart sevapath" in content
    assert "health?check=ready" in content
    # Assert database files are never touched
    assert "rm " not in content or ".sqlite" not in content
    assert "VACUUM" not in content
    assert "restore" not in content.lower() or "symlink" in content.lower()
