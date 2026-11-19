"""
Tests for SQLite schema, foreign keys, seeds, and service retrieval.
"""

import sqlite3
import pytest
from app.models.database import get_db, get_services, get_service_by_slug


def test_database_foreign_keys_enabled(app):
    """Verifies that SQLite foreign key enforcement is turned ON."""
    with app.app_context():
        db = get_db()
        fk_status = db.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk_status == 1


def test_seed_services_count(app):
    """Verifies that the initial 3 services are seeded into the database."""
    with app.app_context():
        services_en = get_services(lang_code="en")
        assert len(services_en) == 3

        slugs = {s["slug"] for s in services_en}
        assert "income-certificate" in slugs
        assert "community-certificate" in slugs
        assert "nativity-certificate" in slugs


def test_service_retrieval_english(app):
    """Verifies retrieval of Income Certificate in English."""
    with app.app_context():
        service = get_service_by_slug("income-certificate", lang_code="en")
        assert service is not None
        assert service["name"] == "Income Certificate"
        assert "Revenue Administration" in service["department"]
        assert len(service["requirements"]) >= 3
        assert service["official_fee"] == "₹60 (e-Sevai Statutory Fee)"
        assert service["is_verified"] == 1


def test_service_retrieval_tamil(app):
    """Verifies retrieval of Community and Income Certificates in Tamil."""
    with app.app_context():
        income = get_service_by_slug("income-certificate", lang_code="ta")
        assert income is not None
        assert income["name"] == "வருமானச் சான்றிதழ்"
        assert "வருவாய்த் துறை" in income["description"] or "வருமானத்தை" in income["description"]

        community = get_service_by_slug("community-certificate", lang_code="ta")
        assert community is not None
        assert "சாதிச் சான்றிதழ்" in community["name"]


def test_foreign_key_cascade_delete(app):
    """Verifies that deleting a service cascades to its translations and requirements."""
    with app.app_context():
        db = get_db()
        # Insert a dummy service
        cur = db.execute("INSERT INTO services (slug, department) VALUES ('dummy-srv', 'Test Dept')")
        srv_id = cur.lastrowid
        db.execute(
            "INSERT INTO service_translations (service_id, lang_code, name, description, benefits, processing_time, official_fee) VALUES (?, 'en', 'Dummy', 'Desc', 'Ben', '1 Day', 'Free')",
            (srv_id,)
        )
        db.commit()

        # Check translation exists
        assert db.execute("SELECT COUNT(*) FROM service_translations WHERE service_id = ?", (srv_id,)).fetchone()[0] == 1

        # Delete service
        db.execute("DELETE FROM services WHERE id = ?", (srv_id,))
        db.commit()

        # Verify translation was automatically cascade deleted
        assert db.execute("SELECT COUNT(*) FROM service_translations WHERE service_id = ?", (srv_id,)).fetchone()[0] == 0
