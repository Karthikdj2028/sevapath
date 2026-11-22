"""
SevaPath Application Factory.
"""

import os
from typing import Optional
from flask import Flask, render_template, request, session
from config import config_by_name, ProductionConfig
from app.models.database import close_db, init_db
from app.translations import get_translation, TRANSLATIONS
from app.core.security import get_csrf_token


def create_app(config_name: Optional[str] = None) -> Flask:
    """
    Application factory for SevaPath.

    Environment resolution:
    - If config_name is None, defaults to SEVAPATH_ENV or 'default'.
    - Fails closed with ValueError if an unknown environment is supplied.
    """
    if config_name is None:
        config_name = os.environ.get("SEVAPATH_ENV", "default")

    # Fail closed on unknown environment names
    if config_name not in config_by_name:
        valid_envs = ", ".join(sorted(config_by_name.keys()))
        raise ValueError(
            f"CRITICAL CONFIGURATION ERROR: Unknown environment '{config_name}'. "
            f"Application refused to start. Valid configurations: [{valid_envs}]."
        )

    config_cls = config_by_name[config_name]
    app = Flask(__name__)
    app.config.from_object(config_cls)

    # Production security validation using robust class hierarchy / identity check
    is_production = (
        config_name == "production"
        or (isinstance(config_cls, type) and issubclass(config_cls, ProductionConfig))
    )
    if is_production:
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret == "sevapath-dev-insecure-secret-key-2026":
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: Production requires a secure SECRET_KEY set in the environment. "
                "Application refused to start with missing or default development key."
            )
        app.config["SECRET_KEY"] = secret

    # Apply ProxyFix middleware only when enabled and hops == 1 (single-hop trusted edge proxy)
    if app.config.get("PROXY_FIX_ENABLED", False):
        hops_env = os.environ.get("PROXY_FIX_HOPS")
        hops = int(hops_env) if hops_env is not None else app.config.get("PROXY_FIX_HOPS", 1)
        if hops != 1:
            raise ValueError(
                f"CRITICAL CONFIGURATION ERROR: Phase 5.1 strictly enforces a single trusted proxy hop (PROXY_FIX_HOPS=1). "
                f"Got: {hops}."
            )
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=hops,
            x_proto=hops,
            x_host=0,     # Disabled: do not trust arbitrary host headers
            x_port=0,     # Disabled: derive port from scheme
            x_prefix=0    # Disabled: no subpath prefix
        )

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Register database teardown
    app.teardown_appcontext(close_db)

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.routes.reports import reports_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)

    # Register context processors for language and template helpers
    @app.context_processor
    def inject_context():
        # Determine language for this request
        lang = request.args.get("lang") or session.get("lang") or request.cookies.get("sevapath_lang") or app.config["DEFAULT_LANGUAGE"]
        if lang not in app.config["SUPPORTED_LANGUAGES"]:
            lang = app.config["DEFAULT_LANGUAGE"]

        def translate(key: str, default: str = "") -> str:
            return get_translation(key, lang=lang, default=default)

        return {
            "current_lang": lang,
            "supported_languages": app.config["SUPPORTED_LANGUAGES"],
            "t": translate,
            "csrf_token": get_csrf_token,
        }

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        lang = session.get("lang", app.config["DEFAULT_LANGUAGE"])
        return render_template("errors/404.html", current_lang=lang), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        lang = session.get("lang", app.config["DEFAULT_LANGUAGE"])
        return render_template("errors/500.html", current_lang=lang), 500

    # Custom CLI commands
    @app.cli.command("init-db")
    def init_db_command():
        """CLI command: flask init-db"""
        init_db(app)
        print("Initialized SQLite database and seeded initial services successfully.")

    return app
