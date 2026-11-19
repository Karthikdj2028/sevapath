"""
SevaPath Application Runner.
"""

import os
from app import create_app
from app.models.database import init_db

env = os.environ.get("FLASK_ENV", "development")
app = create_app(env)

if __name__ == "__main__":
    # Ensure database is initialized before starting
    with app.app_context():
        init_db(app)
    
    port = int(os.environ.get("PORT", 5000))
    debug = env == "development"
    print(f"Starting SevaPath server on http://127.0.0.1:{port} (Debug: {debug})...")
    app.run(host="0.0.0.0", port=port, debug=debug)
