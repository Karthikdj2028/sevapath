"""
Pytest configuration and shared fixtures for SevaPath test suite.
"""

import os
import tempfile
import pytest
from app import create_app
from app.models.database import init_db, close_db, get_db


@pytest.fixture
def app():
    """Creates a test Flask application with a temporary SQLite database."""
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    
    app = create_app("testing")
    app.config["DATABASE_PATH"] = db_path
    app.config["TESTING"] = True

    with app.app_context():
        init_db(app)

    yield app

    # Cleanup temporary test database
    try:
        os.close(db_fd)
        if os.path.exists(db_path):
            os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI test runner."""
    return app.test_cli_runner()
