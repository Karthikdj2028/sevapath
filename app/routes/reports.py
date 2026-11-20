"""
SevaPath Reports Blueprint.

Handles downloadable English PDF reports and browser-printable bilingual checklist views.
"""

from datetime import datetime, timezone
from flask import Blueprint, request, make_response, render_template, abort, current_app

from app.core.security import resolve_citizen_session, set_citizen_cookie
from app.core.pdf_generator import build_preparation_pdf
from app.models.database import (
    get_service_by_slug,
    get_or_create_preparation_session,
    get_service_requirements_with_citizen_state,
    build_service_dfa,
    get_session_completed_keys
)

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/service/<slug>/download-pdf", methods=["GET"])
def download_pdf(slug):
    """
    Generates and downloads an English PDF preparation checklist for the requested service.
    
    Security Guarantees:
    - Cookie-authenticated strictly: ignores any query string or body tokens.
    - Strictly read-only: does not alter database preparation progress.
    - Never includes session tokens, cookie hashes, or personal identifying data.
    - Sets Cache-Control: no-store to prevent caching.
    """
    service = get_service_by_slug(slug, lang_code="en")
    if not service:
        abort(404, description=f"Service '{slug}' not found.")

    # Resolve citizen session from HttpOnly cookie
    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    # Fetch active requirements and progress
    requirements = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code="en")
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code="en")

    completed_keys = get_session_completed_keys(session_id)
    curr_state = dfa.requirements_to_state(completed_keys) if dfa else 0
    progress = dfa.get_progress_summary(curr_state) if dfa else {}

    pdf_bytes = build_preparation_pdf(service, progress, requirements)

    filename = f"sevapath-{slug}-preparation-checklist.pdf"
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"

    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)

    return response


@reports_bp.route("/service/<slug>/print", methods=["GET"])
def print_checklist(slug):
    """
    Renders an accessible, browser-printable bilingual checklist optimized for A4 printing.
    Uses browser's native text engine for high-fidelity Tamil Unicode rendering.
    """
    lang = request.args.get("lang", current_app.config["DEFAULT_LANGUAGE"])
    if lang not in current_app.config["SUPPORTED_LANGUAGES"]:
        lang = current_app.config["DEFAULT_LANGUAGE"]

    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        abort(404, description=f"Service '{slug}' not found.")

    citizen_sess, raw_token, is_new_or_rotated = resolve_citizen_session(request)
    citizen_id = citizen_sess["id"]

    prep_sess = get_or_create_preparation_session(citizen_id, service["id"])
    session_id = prep_sess["id"]

    requirements = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code=lang)
    dfa, _ = build_service_dfa(slug, citizen_session_id=citizen_id, lang_code=lang)

    completed_keys = get_session_completed_keys(session_id)
    curr_state = dfa.requirements_to_state(completed_keys) if dfa else 0
    progress = dfa.get_progress_summary(curr_state) if dfa else {}

    now_utc = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    rendered_html = render_template(
        "print_checklist.html",
        service=service,
        progress=progress,
        requirements=requirements,
        current_lang=lang,
        now_utc=now_utc
    )

    response = make_response(rendered_html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"

    if is_new_or_rotated and raw_token:
        set_citizen_cookie(response, raw_token)

    return response
