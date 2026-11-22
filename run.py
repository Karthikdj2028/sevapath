"""
SevaPath Application Runner for Local Development.
"""

import os
from app import create_app
from app.models.database import init_db

# Local development runner defaults to development environment
env = os.environ.get("SEVAPATH_ENV", "development")
app = create_app(env)

if __name__ == "__main__":
    # Ensure database is initialized before starting
    with app.app_context():
        init_db(app)

    port = int(os.environ.get("PORT", 5000))
    debug = app.config.get("DEBUG", False)
    print(f"Starting SevaPath development server on http://127.0.0.1:{port} (Debug: {debug})...")
    app.run(host="0.0.0.0", port=port, debug=debug)
