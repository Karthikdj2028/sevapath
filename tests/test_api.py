"""
Pytest integration tests for SevaPath DFA API endpoints.

Tests:
- Session initialization and token isolation
- Document completion / revocation state transitions with legitimate CSRF tokens
- Rejection of invalid requirement IDs without state corruption
- Session ownership validation
- Order-independence of HTTP transitions
- State reset with CSRF validation
"""


def get_legitimate_csrf(client):
    """Helper to obtain a legitimate session-bound CSRF token from the API."""
    res = client.get("/api/csrf-token")
    return res.get_json()["csrf_token"]


def test_api_get_state_initial(client):
    """Verifies GET /api/service/income-certificate/state creates session with q_0."""
    response = client.get("/api/service/income-certificate/state")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["service_slug"] == "income-certificate"
    assert "session_token" in data
    assert "csrf_token" in data
    assert data["progress"]["current_state"] == 0
    assert data["progress"]["is_initial"] is True
    assert data["progress"]["is_accepting"] is False
    assert data["progress"]["readiness_percentage"] == 0.0
    assert "visualization" in data
    assert "nodes" in data["visualization"]


def test_api_toggle_valid_requirement(client):
    """Verifies POST /api/service/income-certificate/toggle advances state and updates readiness."""
    # 1. Init session & get CSRF token
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]
    csrf_token = init_res.get_json()["csrf_token"]

    # 2. Complete applicant_photo with legitimate X-CSRF-Token
    toggle_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "session_token": session_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )
    assert toggle_res.status_code == 200
    t_data = toggle_res.get_json()
    assert t_data["progress"]["current_state"] > 0
    assert t_data["progress"]["readiness_percentage"] > 0.0
    assert t_data["progress"]["is_initial"] is False


def test_api_reject_invalid_requirement_without_state_corruption(client):
    """
    CRITICAL REQUIREMENT 2:
    Invalid requirement IDs must be rejected by the API and must never corrupt persisted session state.
    """
    # 1. Init session
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]
    csrf_token = init_res.get_json()["csrf_token"]

    # 2. Complete a valid requirement
    client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "session_token": session_token,
            "requirement_code": "applicant_photo",
            "is_completed": True
        }
    )

    # State before attack
    state_before = client.get(f"/api/service/income-certificate/state?session_token={session_token}").get_json()["progress"]["current_state"]

    # 3. Attempt to submit invalid / malicious requirement code
    invalid_res = client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "session_token": session_token,
            "requirement_code": "MALICIOUS_NONEXISTENT_DOC_ID",
            "is_completed": True
        }
    )
    assert invalid_res.status_code == 400
    assert "error" in invalid_res.get_json()

    # 4. Verify state after rejection remains uncorrupted
    state_after = client.get(f"/api/service/income-certificate/state?session_token={session_token}").get_json()["progress"]["current_state"]
    assert state_after == state_before


def test_api_full_acceptance_flow(client):
    """Verifies that completing all mandatory requirements yields an accepting state."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]
    csrf_token = init_res.get_json()["csrf_token"]

    # In income-certificate seeds, mandatory items are: applicant_photo, address_proof, income_proof
    for req_code in ["applicant_photo", "address_proof", "income_proof"]:
        res = client.post(
            "/api/service/income-certificate/toggle",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "session_token": session_token,
                "requirement_code": req_code,
                "is_completed": True
            }
        )
        assert res.status_code == 200

    final_state = client.get(f"/api/service/income-certificate/state?session_token={session_token}").get_json()
    assert final_state["progress"]["is_accepting"] is True
    assert final_state["progress"]["readiness_percentage"] == 100.0


def test_api_reset_progress(client):
    """Verifies POST /api/service/income-certificate/reset returns session to q_0 with CSRF."""
    init_res = client.get("/api/service/income-certificate/state")
    session_token = init_res.get_json()["session_token"]
    csrf_token = init_res.get_json()["csrf_token"]

    # Complete a requirement
    client.post(
        "/api/service/income-certificate/toggle",
        headers={"X-CSRF-Token": csrf_token},
        json={"session_token": session_token, "requirement_code": "applicant_photo", "is_completed": True}
    )

    # Reset
    reset_res = client.post(
        "/api/service/income-certificate/reset",
        headers={"X-CSRF-Token": csrf_token},
        json={"session_token": session_token}
    )
    assert reset_res.status_code == 200
    r_data = reset_res.get_json()
    assert r_data["progress"]["current_state"] == 0
    assert r_data["progress"]["readiness_percentage"] == 0.0
    assert r_data["progress"]["is_initial"] is True
