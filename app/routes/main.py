"""
SevaPath Main Application Routes.

Handles the citizen dashboard, public services catalog,
service preparation details, language switcher, and system health check.
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, current_app, make_response
from app.models.database import (
    get_db,
    get_services,
    get_service_by_slug,
    get_citizen_dashboard_summary,
    get_or_create_preparation_session,
    get_service_requirements_with_citizen_state,
    build_service_dfa,
    get_session_completed_keys
)
from app.core.security import resolve_citizen_session, set_citizen_cookie
from app.translations import get_translation

main_bp = Blueprint("main", __name__)


def get_current_language() -> str:
    """Resolves active language code: URL param > session > cookie > default (en)."""
    lang_param = request.args.get("lang")
    if lang_param in current_app.config["SUPPORTED_LANGUAGES"]:
        session["lang"] = lang_param
        return lang_param

    if "lang" in session and session["lang"] in current_app.config["SUPPORTED_LANGUAGES"]:
        return session["lang"]

    cookie_lang = request.cookies.get("sevapath_lang")
    if cookie_lang in current_app.config["SUPPORTED_LANGUAGES"]:
        session["lang"] = cookie_lang
        return cookie_lang

    return current_app.config["DEFAULT_LANGUAGE"]


@main_bp.route("/")
def index():
    """
    Homepage & Citizen Preparation Dashboard:
    Displays citizen's preparation progress across Tamil Nadu public services.
    """
    lang = get_current_language()
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    dashboard_services = get_citizen_dashboard_summary(citizen_id, lang_code=lang)

    html = render_template("index.html", services=dashboard_services, current_lang=lang)
    response = make_response(html)
    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)
    return response


@main_bp.route("/services")
def services_directory():
    """Direct alias to public services list on homepage."""
    lang = get_current_language()
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    dashboard_services = get_citizen_dashboard_summary(citizen_id, lang_code=lang)
    html = render_template("index.html", services=dashboard_services, current_lang=lang, scroll_to="services")
    response = make_response(html)
    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)
    return response


@main_bp.route("/service/<slug>")
def service_detail(slug):
    """
    Displays the citizen document preparation experience, interactive applicability decisions,
    DFA state transitions, and report download options for a service.
    """
    lang = get_current_language()
    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return render_template("errors/404.html", message=f"Service '{slug}' not found."), 404

    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    requirements = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code=lang)
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)

    completed_keys = get_session_completed_keys(session_id)
    curr_state = dfa.requirements_to_state(completed_keys) if dfa else 0
    progress = dfa.get_progress_summary(curr_state) if dfa else {}

    html = render_template(
        "service_detail.html",
        service=service,
        requirements=requirements,
        progress=progress,
        current_lang=lang
    )
    response = make_response(html)
    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)
    return response


@main_bp.route("/set-language/<lang_code>")
def set_language(lang_code):
    """Sets language preference in session & cookie and redirects to the previous page."""
    if lang_code in current_app.config["SUPPORTED_LANGUAGES"]:
        session["lang"] = lang_code

    referrer = request.referrer or url_for("main.index")
    response = redirect(referrer)
    response.set_cookie("sevapath_lang", lang_code, max_age=30 * 24 * 3600, samesite="Lax")
    return response


@main_bp.route("/health")
def health_check():
    """System health check endpoint for monitoring, liveness, and readiness probes."""
    check = request.args.get("check")
    if check == "ready":
        try:
            db = get_db()
            db.execute("SELECT 1;").fetchone()
            return jsonify({
                "status": "ready",
                "service": "SevaPath",
                "database": "connected"
            }), 200
        except Exception:
            return jsonify({
                "status": "unavailable",
                "service": "SevaPath",
                "database": "error",
                "message": "Database readiness check failed"
            }), 503

    return jsonify({
        "status": "healthy",
        "service": "SevaPath",
        "version": "1.0.0",
        "database": "sqlite",
        "supported_languages": current_app.config["SUPPORTED_LANGUAGES"],
        "region": "Tamil Nadu, India"
    }), 200
