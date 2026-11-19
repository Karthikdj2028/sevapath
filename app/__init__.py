"""
SevaPath Application Factory.
"""

import os
from flask import Flask, render_template, request, session
from config import config_by_name
from app.models.database import close_db, init_db
from app.translations import get_translation, TRANSLATIONS


def create_app(config_name: str = "default") -> Flask:
    """Application factory for SevaPath."""
    app = Flask(__name__)
    config_cls = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_cls)

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Register database teardown
    app.teardown_appcontext(close_db)

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

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
