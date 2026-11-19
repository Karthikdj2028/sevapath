"""
SevaPath Main Application Routes.

Handles the homepage, language switcher, public services catalog,
service details, and system health check.
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, current_app
from app.models.database import get_services, get_service_by_slug
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
    """Homepage: Renders branding, hero, searchable service cards, how it works, and privacy."""
    lang = get_current_language()
    services = get_services(lang_code=lang)
    return render_template("index.html", services=services, current_lang=lang)


@main_bp.route("/services")
def services_directory():
    """Direct alias to public services list on homepage."""
    lang = get_current_language()
    services = get_services(lang_code=lang)
    return render_template("index.html", services=services, current_lang=lang, scroll_to="services")


@main_bp.route("/service/<slug>")
def service_detail(slug):
    """Displays detailed document requirements and official sources for a single service."""
    lang = get_current_language()
    service = get_service_by_slug(slug, lang_code=lang)
    if not service:
        return render_template("errors/404.html", message=f"Service '{slug}' not found."), 404
    return render_template("service_detail.html", service=service, current_lang=lang)


@main_bp.route("/set-language/<lang_code>")
def set_language(lang_code):
    """Sets language preference in session & cookie and redirects to the previous page."""
    if lang_code in current_app.config["SUPPORTED_LANGUAGES"]:
        session["lang"] = lang_code
    
    # Redirect to referrer or homepage
    referrer = request.referrer or url_for("main.index")
    # Clean out ?lang= from referrer if present to prevent overriding session
    response = redirect(referrer)
    response.set_cookie("sevapath_lang", lang_code, max_age=30 * 24 * 3600, samesite="Lax")
    return response


@main_bp.route("/health")
def health_check():
    """System health check endpoint for monitoring and automated tests."""
    return jsonify({
        "status": "healthy",
        "service": "SevaPath",
        "version": "1.0.0",
        "database": "sqlite",
        "supported_languages": current_app.config["SUPPORTED_LANGUAGES"],
        "region": "Tamil Nadu, India"
    }), 200
