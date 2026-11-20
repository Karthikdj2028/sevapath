"""
SevaPath API Blueprint for Anonymous Citizen DFA Preparation Engine & Regex Validation.

Provides JSON endpoints for:
- Retrieving session CSRF tokens (Strict X-CSRF-Token protected).
- Anonymous cookie-bound citizen session state retrieval.
- Updating requirement applicability decisions ('applicable', 'not_applicable', 'undetermined').
- Marking requirements completed/incomplete with dynamic DFA transitions.
- Resetting service preparation progress.
- Session invalidation (logout).
- Defensive JSON parsing and strict language validation ('en', 'ta').
- Syntax and format validation for mobile numbers and email (zero persistence, zero logging).
"""

from typing import Tuple, Optional, Dict, Any
from flask import Blueprint, request, jsonify, current_app

from app.models.database import (
    get_service_by_slug,
    get_or_create_preparation_session,
    get_service_requirements_with_citizen_state,
    update_session_item_applicability,
    update_session_item_completion,
    reset_service_preparation,
    get_session_completed_keys,
    build_service_dfa,
    revoke_citizen_session_by_id
)
from app.core.security import (
    get_csrf_token,
    generate_csrf_token,
    verify_csrf_token,
    resolve_citizen_session,
    authenticate_citizen_session,
    rotate_citizen_session,
    set_citizen_cookie,
    clear_citizen_cookie,
    CITIZEN_COOKIE_NAME,
    hash_token
)
from app.core.regex_validator import RegexValidator

api_bp = Blueprint("api", __name__, url_prefix="/api")


def parse_json_object(req) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Any, int]]]:
    """
    Defensively parses request body ensuring it is strictly a JSON object (dictionary).
    Rejects arrays (lists), strings, numbers, booleans, null, and malformed JSON with HTTP 400.
    """
    if not req.is_json:
        return None, (jsonify({"error": "Request body must be a valid JSON object."}), 400)

    try:
        data = req.get_json(silent=True)
    except Exception:
        return None, (jsonify({"error": "Malformed JSON payload."}), 400)

    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object (key-value dictionary), not an array or primitive."}), 400)

    return data, None


def parse_language(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[Tuple[Any, int]]]:
    """
    Validates the optional 'lang' parameter.
    Only 'en' and 'ta' are accepted. Defaults safely to DEFAULT_LANGUAGE if omitted.
    """
    if "lang" in data and data["lang"] is not None:
        lang = data["lang"]
        if lang not in current_app.config["SUPPORTED_LANGUAGES"]:
            supported = ", ".join(f"'{l}'" for l in current_app.config["SUPPORTED_LANGUAGES"])
            return None, (jsonify({"error": f"Invalid language code '{lang}'. Supported languages: {supported}."}), 400)
        return lang, None
    return current_app.config["DEFAULT_LANGUAGE"], None


@api_bp.route("/csrf-token", methods=["GET"])
def get_csrf():
    """
    Returns the active session CSRF token bound to the citizen session identity.
    Enforces Cache-Control: no-store to prevent token caching by proxies/browsers.
    """
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"] if citizen_sess else None
    token = get_csrf_token(citizen_id)
    response = jsonify({"csrf_token": token})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)
    return response, 200


@api_bp.route("/validate-format", methods=["POST"])
def validate_format_endpoint():
    """
    Validates input format for supported fields (phone, email).
    Never stores, caches, or logs submitted values.
    """
    data, err = parse_json_object(request)
    if err:
        return err

    lang, lang_err = parse_language(data)
    if lang_err:
        return lang_err

    field_type = data.get("field_type")
    value = data.get("value")

    if not field_type:
        return jsonify({"error": "'field_type' parameter is required."}), 400

    result = RegexValidator.validate_format(str(field_type), value)
    response = jsonify(result.to_dict(lang=lang))
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@api_bp.route("/citizen/session", methods=["GET"])
def get_citizen_session_info():
    """
    Returns non-sensitive metadata about the active anonymous citizen session.
    Never exposes raw tokens or token hashes.
    """
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    response = jsonify({
        "status": "success",
        "authenticated": True,
        "expires_at": citizen_sess["expires_at"]
    })
    response.headers["Cache-Control"] = "no-store, private"
    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)
    return response, 200


@api_bp.route("/citizen/logout", methods=["POST"])
def logout_citizen():
    """
    Revokes the current citizen session identity and clears the session cookie.
    Requires authenticated citizen session and strict CSRF validation.
    """
    citizen_sess, auth_err = authenticate_citizen_session(request)
    if auth_err:
        return jsonify({"error": f"Authentication required. {auth_err}"}), 401

    submitted_csrf = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(submitted_csrf, citizen_session_id=citizen_sess["id"]):
        return jsonify({"error": "CSRF token missing or invalid. Requires valid 'X-CSRF-Token' header."}), 403

    revoke_citizen_session_by_id(citizen_sess["id"])

    response = jsonify({"status": "success", "message": "Citizen session revoked."})
    response.headers["Cache-Control"] = "no-store, private"
    clear_citizen_cookie(response)
    return response, 200


@api_bp.route("/citizen/rotate", methods=["POST"])
def rotate_citizen_token_endpoint():
    """
    Explicitly rotates the citizen's anonymous session token using race-safe compare-and-swap.
    Invalidates the old token immediately for mutations.
    Requires authenticated citizen session and strict CSRF validation.
    """
    citizen_sess, auth_err = authenticate_citizen_session(request)
    if auth_err:
        return jsonify({"error": f"Authentication required. {auth_err}"}), 401

    submitted_csrf = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(submitted_csrf, citizen_session_id=citizen_sess["id"]):
        return jsonify({"error": "CSRF token missing or invalid. Requires valid 'X-CSRF-Token' header."}), 403

    raw_cookie = request.cookies.get(CITIZEN_COOKIE_NAME)
    new_raw_token, updated_sess, err = rotate_citizen_session(raw_cookie)
    if err or not new_raw_token:
        return jsonify({"error": f"Rotation failed: {err}"}), 409

    # Re-bind CSRF token to rotated identity
    csrf_token = generate_csrf_token(updated_sess["id"])

    response = jsonify({
        "status": "success",
        "message": "Citizen session token successfully rotated.",
        "expires_at": updated_sess["expires_at"],
        "csrf_token": csrf_token
    })
    response.headers["Cache-Control"] = "no-store, private"
    set_citizen_cookie(response, new_raw_token)
    return response, 200


@api_bp.route("/service/<slug>/state", methods=["GET"])
def get_service_state(slug):
    """
    Retrieves the current DFA state and citizen preparation progress for a service.
    Authenticated exclusively via HttpOnly cookie; ignores legacy URL query parameters.
    """
    lang = request.args.get("lang", current_app.config["DEFAULT_LANGUAGE"])
    if lang not in current_app.config["SUPPORTED_LANGUAGES"]:
        lang = current_app.config["DEFAULT_LANGUAGE"]

    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # Resolve anonymous citizen session
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    # Build DFA with citizen applicability
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)
    completed_keys = get_session_completed_keys(session_id)
    current_state = dfa.requirements_to_state(completed_keys) if dfa else 0

    progress = dfa.get_progress_summary(current_state) if dfa else {}
    graph = dfa.get_visualization_graph(current_state) if dfa else {}
    requirements = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code=lang)

    csrf_tok = get_csrf_token()

    response = jsonify({
        "status": "success",
        "service_slug": slug,
        "service_name": service["name"],
        "csrf_token": csrf_tok,
        "progress": progress,
        "visualization": graph,
        "requirements": requirements,
        "official_source": {
            "portal": service["portal_name"],
            "url": service["source_url"],
            "verified_date": service["verification_date"]
        }
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"

    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)

    return response, 200


@api_bp.route("/service/<slug>/applicability", methods=["POST"])
def update_applicability(slug):
    """
    Updates the citizen-specific applicability decision for a requirement.
    Options: 'applicable', 'not_applicable', 'undetermined'.
    Strictly X-CSRF-Token and authenticated cookie-session protected.
    """
    # 1. Authenticate Citizen Session (Strict HttpOnly Cookie)
    citizen_sess, auth_err = authenticate_citizen_session(request)
    if auth_err:
        return jsonify({"error": f"Authentication required: {auth_err}"}), 401

    # 2. Strict CSRF Header Verification bound to citizen identity
    submitted_csrf = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(submitted_csrf, citizen_session_id=citizen_sess["id"]):
        return jsonify({"error": "CSRF token missing or invalid. Requires valid 'X-CSRF-Token' header."}), 403

    # 3. Defensive JSON Parsing
    data, err = parse_json_object(request)
    if err:
        return err

    # 4. Language Validation
    lang, lang_err = parse_language(data)
    if lang_err:
        return lang_err

    req_code = data.get("requirement_code")
    applicability = data.get("applicability")

    if not req_code or not applicability:
        return jsonify({"error": "Both 'requirement_code' and 'applicability' are required."}), 400

    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # 5. Access citizen preparation session
    citizen_id = citizen_sess["id"]
    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    # 6. Update applicability in database
    success, err_msg = update_session_item_applicability(session_id, service["id"], req_code, applicability)
    if not success:
        return jsonify({"error": err_msg}), 400

    # 7. Rebuild DFA and return updated progress
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)
    completed_keys = get_session_completed_keys(session_id)
    current_state = dfa.requirements_to_state(completed_keys) if dfa else 0

    progress = dfa.get_progress_summary(current_state) if dfa else {}
    graph = dfa.get_visualization_graph(current_state) if dfa else {}
    requirements = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code=lang)

    response = jsonify({
        "status": "success",
        "service_slug": slug,
        "progress": progress,
        "visualization": graph,
        "requirements": requirements
    })
    response.headers["Cache-Control"] = "no-store, private"
    return response, 200


@api_bp.route("/service/<slug>/toggle", methods=["POST"])
def toggle_requirement(slug):
    """
    Applies completion or revocation of a document to the DFA and persists the transition.
    Strictly X-CSRF-Token and authenticated cookie-session protected.
    """
    # 1. Authenticate Citizen Session (Strict HttpOnly Cookie)
    citizen_sess, auth_err = authenticate_citizen_session(request)
    if auth_err:
        return jsonify({"error": f"Authentication required: {auth_err}"}), 401

    # 2. Strict CSRF Header Verification bound to citizen identity
    submitted_csrf = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(submitted_csrf, citizen_session_id=citizen_sess["id"]):
        return jsonify({"error": "CSRF token missing or invalid. Requires valid 'X-CSRF-Token' header."}), 403

    # 3. Defensive JSON Parsing
    data, err = parse_json_object(request)
    if err:
        return err

    # 4. Language Validation
    lang, lang_err = parse_language(data)
    if lang_err:
        return lang_err

    req_code = data.get("requirement_code")
    is_completed = bool(data.get("is_completed", True))
    selected_alt = data.get("selected_alternative")

    if not req_code:
        return jsonify({"error": "'requirement_code' is required."}), 400

    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # 5. Access citizen preparation session
    citizen_id = citizen_sess["id"]
    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    # 6. Update requirement completion in SQLite
    success, err_msg = update_session_item_completion(session_id, service["id"], req_code, is_completed, selected_alt)
    if not success:
        return jsonify({"error": err_msg}), 400

    # 7. Rebuild DFA and compute new state
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)
    completed_keys = get_session_completed_keys(session_id)
    current_state = dfa.requirements_to_state(completed_keys) if dfa else 0

    progress = dfa.get_progress_summary(current_state) if dfa else {}
    graph = dfa.get_visualization_graph(current_state) if dfa else {}

    response = jsonify({
        "status": "success",
        "service_slug": slug,
        "progress": progress,
        "visualization": graph
    })
    response.headers["Cache-Control"] = "no-store, private"
    return response, 200


@api_bp.route("/service/<slug>/reset", methods=["POST"])
def reset_progress(slug):
    """
    Resets progress and applicability for this service back to initial state.
    Strictly X-CSRF-Token and authenticated cookie-session protected.
    """
    # 1. Authenticate Citizen Session (Strict HttpOnly Cookie)
    citizen_sess, auth_err = authenticate_citizen_session(request)
    if auth_err:
        return jsonify({"error": f"Authentication required: {auth_err}"}), 401

    # 2. Strict CSRF Header Verification bound to citizen identity
    submitted_csrf = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(submitted_csrf, citizen_session_id=citizen_sess["id"]):
        return jsonify({"error": "CSRF token missing or invalid. Requires valid 'X-CSRF-Token' header."}), 403

    # 3. Defensive JSON Parsing
    data, err = parse_json_object(request)
    if err:
        return err

    # 4. Language Validation
    lang, lang_err = parse_language(data)
    if lang_err:
        return lang_err

    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return jsonify({"error": f"Service '{slug}' not found."}), 404

    # 5. Access citizen preparation session
    citizen_id = citizen_sess["id"]
    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    # 6. Reset service preparation
    reset_service_preparation(session_id, service["id"])

    # 7. Build DFA with clean initial state
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)
    progress = dfa.get_progress_summary(dfa.q_0) if dfa else {}
    graph = dfa.get_visualization_graph(dfa.q_0) if dfa else {}

    response = jsonify({
        "status": "success",
        "service_slug": slug,
        "progress": progress,
        "visualization": graph
    })
    response.headers["Cache-Control"] = "no-store, private"
    return response, 200
