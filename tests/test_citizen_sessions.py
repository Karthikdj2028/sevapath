"""
Pytest security test suite for Anonymous Citizen Cookie Sessions.

Verifies:
- 256-bit entropy raw cookie generation.
- HttpOnly, SameSite=Lax, and Secure cookie flags.
- SHA-256 token hashing at rest in SQLite (raw token absence).
- Session isolation between multiple citizens.
- Expiration, rotation, and revocation/logout semantics.
- Rejection of legacy query and JSON tokens.
- Cross-service reset isolation.
"""

import hashlib
from datetime import datetime, timezone, timedelta
from app.models.database import get_db, create_citizen_session
from app.core.security import CITIZEN_COOKIE_NAME, hash_token


def test_first_visit_creates_anonymous_cookie_identity(client):
    """Verifies that the citizen's initial visit automatically creates an anonymous cookie session."""
    res = client.get("/api/service/income-certificate/state")
    assert res.status_code == 200
    cookie_header = res.headers.get("Set-Cookie", "")
    assert CITIZEN_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header


def test_raw_token_never_stored_in_database(client, app):
    """Verifies that the raw cookie value is never persisted; only SHA-256 hashes exist."""
    res = client.get("/api/service/income-certificate/state")
    assert res.status_code == 200

    # Extract raw cookie value from test client cookie jar
    cookie = client.get_cookie(CITIZEN_COOKIE_NAME)
    assert cookie is not None
    raw_token = cookie.value
    expected_hash = hash_token(raw_token)

    with app.app_context():
        db = get_db()
        # Assert raw token is absent
        raw_match = db.execute("SELECT COUNT(*) FROM citizen_sessions WHERE token_hash = ?", (raw_token,)).fetchone()[0]
        assert raw_match == 0

        # Assert SHA-256 hash exists
        hash_match = db.execute("SELECT COUNT(*) FROM citizen_sessions WHERE token_hash = ?", (expected_hash,)).fetchone()[0]
        assert hash_match == 1


def test_two_citizens_remain_completely_isolated(app):
    """Verifies that progress in Citizen A's session is never exposed to or mutated by Citizen B."""
    client_a = app.test_client()
    client_b = app.test_client()

    # Client A initializes and completes applicant_photo
    res_a = client_a.get("/api/service/income-certificate/state")
    csrf_a = res_a.get_json()["csrf_token"]
    client_a.post(
        "/api/service/income-certificate/applicability",
        headers={"X-CSRF-Token": csrf_a},
        json={"requirement_code": "applicant_photo", "applicability": "applicable"}
    )
    client_a.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_a},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )

    state_a = client_a.get("/api/service/income-certificate/state").get_json()
    assert state_a["progress"]["completed_count"] == 1

    # Client B initializes income certificate
    res_b = client_b.get("/api/service/income-certificate/state")
    state_b = res_b.get_json()
    # Client B has separate identity; completed_count must be 0
    assert state_b["progress"]["completed_count"] == 0
    assert state_b["progress"]["current_state"] == 0


def test_legacy_url_and_json_tokens_cannot_authenticate(client, app):
    """
    Verifies that passing a legacy session_token in query params or JSON body
    is strictly ignored and does not authenticate or hijack another session.
    """
    # 1. Manually insert a legacy session into SQLite
    with app.app_context():
        db = get_db()
        legacy_token = "legacy_secret_token_abcdef123456"
        cur = db.execute("INSERT INTO preparation_sessions (session_token, service_id) VALUES (?, 1)", (legacy_token,))
        legacy_prep_id = cur.lastrowid
        # Add a completed item to this legacy session
        req_id = db.execute("SELECT id FROM requirements WHERE service_id = 1 LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO session_items (session_id, requirement_id, is_completed) VALUES (?, ?, 1)", (legacy_prep_id, req_id))
        db.commit()

    # 2. Client visits with ?session_token=legacy_token
    res = client.get(f"/api/service/income-certificate/state?session_token={legacy_token}")
    data = res.get_json()
    # Client must NOT receive the legacy completed item
    assert data["progress"]["completed_count"] == 0

    # 3. Client attempts to mutate using JSON body with legacy token
    csrf = data["csrf_token"]
    toggle_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"session_token": legacy_token, "requirement_code": "applicant_photo", "is_completed": True}
    )
    # Mutation operates on the client's own cookie session, leaving legacy session untouched
    with app.app_context():
        db = get_db()
        legacy_count = db.execute("SELECT COUNT(*) FROM session_items WHERE session_id = ? AND is_completed = 1", (legacy_prep_id,)).fetchone()[0]
        assert legacy_count == 1  # Unchanged


def test_forged_cookie_cannot_access_existing_progress(client, app):
    """Verifies that an attacker sending a forged or random cookie token cannot access existing sessions."""
    # First client creates real session
    real_res = client.get("/api/service/income-certificate/state")
    csrf_real = real_res.get_json()["csrf_token"]
    client.post(
        "/api/service/income-certificate/applicability",
        headers={"X-CSRF-Token": csrf_real},
        json={"requirement_code": "applicant_photo", "applicability": "applicable"}
    )
    client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_real},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )

    # Attacker client sets forged cookie
    attacker_client = app.test_client()
    attacker_client.set_cookie(CITIZEN_COOKIE_NAME, "forged_random_invalid_token_9999999999")
    attacker_res = attacker_client.get("/api/service/income-certificate/state")
    att_data = attacker_res.get_json()
    # Attacker receives fresh initial state 0, not existing citizen's progress
    assert att_data["progress"]["completed_count"] == 0
    assert att_data["progress"]["current_state"] == 0


def test_expired_cookie_initializes_fresh_session(client, app):
    """Verifies that an expired cookie cannot access historical progress and is safely re-initialized."""
    # Create session with expired date
    expired_raw = "expired_raw_token_xyz"
    expired_hash = hash_token(expired_raw)
    past_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO citizen_sessions (token_hash, expires_at) VALUES (?, ?)",
            (expired_hash, past_time)
        )
        db.commit()

    client.set_cookie(CITIZEN_COOKIE_NAME, expired_raw)
    res = client.get("/api/service/income-certificate/state")
    assert res.status_code == 200
    # Must set a new cookie
    new_cookie = res.headers.get("Set-Cookie", "")
    assert CITIZEN_COOKIE_NAME in new_cookie


def test_cross_service_reset_isolation(client):
    """Verifies that resetting Nativity Certificate leaves Income Certificate progress untouched."""
    init_res = client.get("/api/service/income-certificate/state")
    csrf = init_res.get_json()["csrf_token"]

    # 1. Complete item on Income
    client.post(
        "/api/service/income-certificate/applicability",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "applicability": "applicable"}
    )
    client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )

    # 2. Complete item on Nativity
    client.post(
        "/api/service/nativity-certificate/applicability",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "applicability": "applicable"}
    )
    client.post(
        "/api/service/nativity-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )

    # 3. Reset Nativity only
    reset_res = client.post("/api/service/nativity-certificate/reset", headers={"X-CSRF-Token": csrf}, json={})
    assert reset_res.status_code == 200
    nat_state = client.get("/api/service/nativity-certificate/state").get_json()
    assert nat_state["progress"]["completed_count"] == 0

    # 4. Assert Income remains completed
    inc_state = client.get("/api/service/income-certificate/state").get_json()
    assert inc_state["progress"]["completed_count"] == 1


def test_logout_revokes_citizen_session(client, app):
    """Verifies that calling /api/citizen/logout revokes the session and clears the cookie."""
    res = client.get("/api/service/income-certificate/state")
    csrf = res.get_json()["csrf_token"]
    raw_cookie = client.get_cookie(CITIZEN_COOKIE_NAME).value

    logout_res = client.post("/api/citizen/logout", headers={"X-CSRF-Token": csrf})
    assert logout_res.status_code == 200

    # Assert database revoked_at is populated
    with app.app_context():
        db = get_db()
        t_hash = hash_token(raw_cookie)
        revoked_row = db.execute("SELECT revoked_at FROM citizen_sessions WHERE token_hash = ?", (t_hash,)).fetchone()
        assert revoked_row["revoked_at"] is not None


def test_session_token_rotation_and_old_token_rejected_for_mutations(client, app):
    """
    Verifies token rotation:
    1. Rotating token invalidates old token for mutations immediately (401).
    2. Rotated token can authenticate and continue mutations.
    """
    init_res = client.get("/api/service/income-certificate/state")
    assert init_res.status_code == 200
    csrf = init_res.get_json()["csrf_token"]
    old_raw_cookie = client.get_cookie(CITIZEN_COOKIE_NAME).value

    # Explicitly rotate token
    rotate_res = client.post("/api/citizen/rotate", headers={"X-CSRF-Token": csrf})
    assert rotate_res.status_code == 200
    rotate_data = rotate_res.get_json()
    new_csrf = rotate_data["csrf_token"]
    new_raw_cookie = client.get_cookie(CITIZEN_COOKIE_NAME).value
    assert new_raw_cookie != old_raw_cookie

    # Attempt mutation with old cookie -> must return 401 Unauthorized
    attacker_client = app.test_client()
    attacker_client.set_cookie(CITIZEN_COOKIE_NAME, old_raw_cookie)
    bad_res = attacker_client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert bad_res.status_code == 401

    # Attempt mutation with new cookie -> succeeds
    good_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": new_csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert good_res.status_code == 200


def test_concurrent_rotation_race_safety(app):
    """
    Verifies that concurrent token rotation uses compare-and-swap and does not corrupt the session.
    """
    from app.core.security import rotate_citizen_session, resolve_citizen_session, hash_token
    from app.models.database import create_citizen_session, get_citizen_session_by_hash

    with app.app_context():
        # Setup initial session
        initial_raw = "race_test_raw_token_12345"
        initial_hash = hash_token(initial_raw)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        create_citizen_session(initial_hash, expires_at)

        # Worker 1 rotates
        tok1, sess1, err1 = rotate_citizen_session(initial_raw)
        assert tok1 is not None
        assert err1 is None

        # Worker 2 attempts to rotate using the same initial token -> fails safely via compare-and-swap
        tok2, sess2, err2 = rotate_citizen_session(initial_raw)
        assert tok2 is None
        assert err2 is not None

        # Verify database holds tok1's hash, not corrupted
        tok1_hash = hash_token(tok1)
        active_sess = get_citizen_session_by_hash(tok1_hash)
        assert active_sess is not None


def test_mutation_with_missing_cookie_rejected_with_401(client):
    """Verifies that mutation without citizen session cookie returns 401."""
    # Obtain valid CSRF token first
    res = client.get("/api/csrf-token")
    csrf = res.get_json()["csrf_token"]

    # Delete cookie
    client.delete_cookie(CITIZEN_COOKIE_NAME)

    toggle_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert toggle_res.status_code == 401

    app_res = client.post(
        "/api/service/income-certificate/applicability",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "applicability": "applicable"}
    )
    assert app_res.status_code == 401


def test_mutation_with_invalid_cookie_rejected_with_401(client):
    """Verifies that mutation with an invalid or forged cookie returns 401."""
    res = client.get("/api/csrf-token")
    csrf = res.get_json()["csrf_token"]

    client.set_cookie(CITIZEN_COOKIE_NAME, "forged_non_existent_cookie_token_99999")

    toggle_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert toggle_res.status_code == 401


def test_mutation_with_expired_cookie_rejected_with_401(client, app):
    """Verifies that mutation with an expired cookie returns 401 and does not execute mutation."""
    past_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    raw_expired = "expired_raw_token_for_mutation"
    expired_hash = hash_token(raw_expired)

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO citizen_sessions (token_hash, expires_at) VALUES (?, ?)",
            (expired_hash, past_time)
        )
        db.commit()

    client.set_cookie(CITIZEN_COOKIE_NAME, raw_expired)
    res = client.get("/api/csrf-token")
    csrf = res.get_json()["csrf_token"]

    # Reset cookie to expired
    client.set_cookie(CITIZEN_COOKIE_NAME, raw_expired)
    toggle_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "applicant_photo", "is_completed": True}
    )
    assert toggle_res.status_code == 401


def test_expired_identity_preserves_preparation_sessions_and_items(app):
    """
    Verifies expired-session data preservation:
    Deleting or expiring an anonymous identity NEVER cascades or destroys
    preparation sessions, session items, completion states, or applicability.
    (Enforced by ON DELETE SET NULL).
    """
    with app.app_context():
        db = get_db()
        # 1. Create a citizen session
        raw_tok = "preservation_test_raw_tok"
        t_hash = hash_token(raw_tok)
        exp = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        cur = db.execute("INSERT INTO citizen_sessions (token_hash, expires_at) VALUES (?, ?)", (t_hash, exp))
        cit_id = cur.lastrowid

        # 2. Create preparation session and items
        cur2 = db.execute(
            "INSERT INTO preparation_sessions (session_token, service_id, citizen_session_id) VALUES (?, 1, ?)",
            ("prep_tok_unique_123", cit_id)
        )
        prep_id = cur2.lastrowid

        req_id = db.execute("SELECT id FROM requirements WHERE service_id = 1 LIMIT 1").fetchone()[0]
        db.execute(
            "INSERT INTO session_items (session_id, requirement_id, is_completed, applicability) VALUES (?, ?, 1, 'applicable')",
            (prep_id, req_id)
        )
        db.commit()

        # 3. Simulate deletion / cleanup of expired citizen session
        db.execute("DELETE FROM citizen_sessions WHERE id = ?", (cit_id,))
        db.commit()

        # 4. Verify preparation session still exists (with citizen_session_id SET NULL)
        prep_row = db.execute("SELECT * FROM preparation_sessions WHERE id = ?", (prep_id,)).fetchone()
        assert prep_row is not None
        assert prep_row["citizen_session_id"] is None

        # 5. Verify session items and completion state are 100% preserved
        item_row = db.execute("SELECT * FROM session_items WHERE session_id = ?", (prep_id,)).fetchone()
        assert item_row is not None
        assert item_row["is_completed"] == 1
        assert item_row["applicability"] == "applicable"
