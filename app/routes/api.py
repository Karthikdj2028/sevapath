"""
SevaPath API Blueprint for DFA Preparation Engine & Regex Validation.

Provides JSON endpoints for:
- Retrieving cryptographically random session CSRF tokens.
- Initializing or retrieving preparation session states.
- Marking requirements completed/incomplete with DFA transitions (CSRF protected).
- Resetting preparation progress (CSRF protected).
- Syntax and format validation for mobile numbers and email (no persistence, zero logging).
"""

from flask import Blueprint, request, jsonify, current_app
from app.models.database import (
    get_service_by_slug,
    get_or_create_session,
    get_session_completed_keys,
    update_session_requirement,
    reset_session_progress,
    build_service_dfa
)
from app.core.security import get_csrf_token, verify_csrf_token
from app.core.regex_validator import RegexValidator

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/csrf-token", methods=["GET"])
def get_csrf():
    """
    Returns the active session CSRF token.
    Used by browser scripts and automated test clients to obtain legitimate tokens.
    """
    token = get_csrf_token()
    return jsonify({"csrf_token": token}), 200


@api_bp.route("/validate-format", methods=["POST"])
def validate_format_endpoint():
    """
    Validates input format for supported fields (phone, email).
    
    Privacy & Security Guarantees:
    - Never stores, caches, or logs submitted values.
    - Never logs request body containing personal data.
    - Does not echo sensitive inputs in error responses unnecessarily.
    - Does not collect or validate Aadhaar numbers.
    """
    data = request.get_json(silent=True) or {}
    field_type = data.get("field_type")
    value = data.get("value")
    lang = data.get("lang", current_app.config["DEFAULT_LANGUAGE"])

    if not field_type:
        return jsonify({"error": "'field_type' parameter is required."}), 400

    result = RegexValidator.validate_format(str(field_type), value)
    return jsonify(result.to_dict(lang=lang)), 200


@api_bp.route("/service/<slug>/state", methods=["GET"])
def get_service_state(slug):
    """
    Retrieves the current DFA state and progress for a service and session.
    """
    lang = request.args.get("lang", current_app.config["DEFAULT_LANGUAGE"])
    session_token = request.args.get("session_token")
    
    # Conditional flags
    is_it_assessee = request.args.get("is_it_assessee", "0") == "1"
    active_conditions = {"is_it_assessee": is_it_assessee}

    dfa, service = build_service_dfa(slug, lang_code=lang, active_conditions=active_conditions)
    if not dfa or not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # Get or create isolated session
    sess = get_or_create_session(service["id"], session_token)
    session_id = sess["session_id"]
    active_token = sess["session_token"]

    # Fetch completed keys from SQLite session
    completed_keys = get_session_completed_keys(session_id)
    
    # Compute DFA state bitmask
    current_state = dfa.requirements_to_state(completed_keys)

    # Progress summary and visualization graph
    progress = dfa.get_progress_summary(current_state)
    graph = dfa.get_visualization_graph(current_state)

    # Ensure CSRF token is initialized for this session
    csrf_tok = get_csrf_token()

    return jsonify({
        "status": "success",
        "service_slug": slug,
        "service_name": service["name"],
        "session_token": active_token,
        "csrf_token": csrf_tok,
        "progress": progress,
        "visualization": graph,
        "official_source": {
            "portal": service["portal_name"],
            "url": service["source_url"],
            "verified_date": service["verification_date"]
        }
    }), 200


@api_bp.route("/service/<slug>/toggle", methods=["POST"])
def toggle_requirement(slug):
    """
    Applies a completion or revocation event to the DFA and persists the transition.
    
    Security & Safety:
    - Enforces cryptographic CSRF token validation (X-CSRF-Token header or body).
    - Missing or invalid CSRF tokens receive HTTP 403 Forbidden.
    - Validates anonymous session ownership against service_id.
    - Rejects invalid requirement IDs with 400 Bad Request without corrupting state.
    """
    data = request.get_json(silent=True) or {}
    
    # 1. CSRF Verification
    submitted_csrf = request.headers.get("X-CSRF-Token") or data.get("csrf_token")
    if not verify_csrf_token(submitted_csrf):
        return jsonify({"error": "CSRF token missing or invalid."}), 403

    session_token = data.get("session_token")
    req_code = data.get("requirement_code")
    is_completed = bool(data.get("is_completed", True))
    lang = data.get("lang", current_app.config["DEFAULT_LANGUAGE"])

    if not session_token or not req_code:
        return jsonify({"error": "Both 'session_token' and 'requirement_code' are required."}), 400

    dfa, service = build_service_dfa(slug, lang_code=lang)
    if not dfa or not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # 2. Validate session ownership
    sess = get_or_create_session(service["id"], session_token)
    if sess["session_token"] != session_token:
        return jsonify({"error": "Unauthorized or mismatched session token."}), 403

    session_id = sess["session_id"]

    # 3. Update database session (rejects invalid requirement_code without corrupting state)
    success, err_msg = update_session_requirement(session_id, service["id"], req_code, is_completed)
    if not success:
        return jsonify({"error": err_msg}), 400

    # Retrieve updated completed keys and compute new DFA state
    completed_keys = get_session_completed_keys(session_id)
    current_state = dfa.requirements_to_state(completed_keys)

    progress = dfa.get_progress_summary(current_state)
    graph = dfa.get_visualization_graph(current_state)

    return jsonify({
        "status": "success",
        "service_slug": slug,
        "session_token": session_token,
        "progress": progress,
        "visualization": graph,
    }), 200


@api_bp.route("/service/<slug>/reset", methods=["POST"])
def reset_progress(slug):
    """
    Resets the session state back to q_0 (all documents uncompleted).
    
    Security & Safety:
    - Enforces cryptographic CSRF token validation (X-CSRF-Token header or body).
    - Missing or invalid CSRF tokens receive HTTP 403 Forbidden.
    - Validates anonymous session ownership against service_id.
    """
    data = request.get_json(silent=True) or {}

    # 1. CSRF Verification
    submitted_csrf = request.headers.get("X-CSRF-Token") or data.get("csrf_token")
    if not verify_csrf_token(submitted_csrf):
        return jsonify({"error": "CSRF token missing or invalid."}), 403

    session_token = data.get("session_token")
    lang = data.get("lang", current_app.config["DEFAULT_LANGUAGE"])

    if not session_token:
        return jsonify({"error": "'session_token' is required."}), 400

    dfa, service = build_service_dfa(slug, lang_code=lang)
    if not dfa or not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # 2. Validate session ownership
    sess = get_or_create_session(service["id"], session_token)
    if sess["session_token"] != session_token:
        return jsonify({"error": "Unauthorized session token."}), 403

    reset_session_progress(sess["session_id"], service["id"])

    # Initial state q_0
    progress = dfa.get_progress_summary(dfa.q_0)
    graph = dfa.get_visualization_graph(dfa.q_0)

    return jsonify({
        "status": "success",
        "service_slug": slug,
        "session_token": session_token,
        "progress": progress,
        "visualization": graph,
    }), 200
