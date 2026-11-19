"""
Tests for Flask application factory, routes, and health check.
"""

def test_app_startup(app):
    """Verifies that the Flask app initializes successfully with testing config."""
    assert app is not None
    assert app.config["TESTING"] is True


def test_health_check_endpoint(client):
    """Verifies that the /health endpoint returns HTTP 200 and expected metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "SevaPath"
    assert "en" in data["supported_languages"]
    assert "ta" in data["supported_languages"]


def test_homepage_response(client):
    """Verifies that the homepage loads with status code 200 and brand title."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "SevaPath" in html
    assert "Tamil Nadu" in html


def test_404_error_handling(client):
    """Verifies that requesting a non-existent URL returns 404 with custom error page."""
    response = client.get("/non-existent-service-url")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "404" in html
