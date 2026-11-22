"""
SevaPath Production WSGI Entry Point.

Invoked by Gunicorn or other production WSGI application servers.
Exposes the application callable 'app'.

Zero side-effects at import time:
Database initialization and migrations must be performed as an explicit release
step prior to starting WSGI worker processes (e.g. `flask --app wsgi:app init-db`).
"""

import os
from app import create_app

# Strictly enforce production environment in the production WSGI entry point
env = os.environ.get("SEVAPATH_ENV", "production")
if env != "production":
    raise RuntimeError(
        f"CRITICAL WSGI INVOCATION ERROR: wsgi.py is strictly restricted to production. "
        f"Attempted to initialize with SEVAPATH_ENV='{env}'. Use run.py for local development."
    )

app = create_app("production")
