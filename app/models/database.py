"""
SevaPath SQLite Database Layer.

Provides schema creation, foreign key enforcement, database connection pooling,
and query helpers for services, requirements, and translations.
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional
from flask import g, current_app


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    department TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    lang_code TEXT NOT NULL CHECK(lang_code IN ('en', 'ta')),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    benefits TEXT,
    processing_time TEXT NOT NULL,
    official_fee TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    UNIQUE (service_id, lang_code)
);

CREATE TABLE IF NOT EXISTS official_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    portal_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    verification_date TEXT NOT NULL,
    jurisdiction TEXT NOT NULL DEFAULT 'Tamil Nadu, India',
    is_verified INTEGER DEFAULT 1,
    notes TEXT,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    requirement_code TEXT NOT NULL,
    is_mandatory INTEGER DEFAULT 1,
    document_type TEXT NOT NULL,
    order_seq INTEGER DEFAULT 0,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    UNIQUE (service_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS requirement_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_id INTEGER NOT NULL,
    lang_code TEXT NOT NULL CHECK(lang_code IN ('en', 'ta')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    help_text TEXT,
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    UNIQUE (requirement_id, lang_code)
);

CREATE TABLE IF NOT EXISTS preparation_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token TEXT UNIQUE NOT NULL,
    service_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    requirement_id INTEGER NOT NULL,
    is_completed INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES preparation_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    UNIQUE (session_id, requirement_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_services_slug ON services(slug);
CREATE INDEX IF NOT EXISTS idx_service_translations_lang ON service_translations(service_id, lang_code);
CREATE INDEX IF NOT EXISTS idx_requirements_service ON requirements(service_id);
CREATE INDEX IF NOT EXISTS idx_req_translations_lang ON requirement_translations(requirement_id, lang_code);
"""


def get_db() -> sqlite3.Connection:
    """Returns an active SQLite database connection for the current Flask request context."""
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        # Enforce foreign key constraints
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Closes the active database connection if open."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db_connection(db_path: str) -> sqlite3.Connection:
    """Helper to get a direct SQLite connection (outside request context)."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(app=None):
    """Initializes schema and seeds initial verified/demo services."""
    if app:
        with app.app_context():
            db = get_db()
            db.executescript(SCHEMA_SQL)
            from app.data.seeds import seed_initial_services
            seed_initial_services(db)
            db.commit()
    else:
        db = get_db()
        db.executescript(SCHEMA_SQL)
        from app.data.seeds import seed_initial_services
        seed_initial_services(db)
        db.commit()


# --- Query Helpers ---

def get_services(lang_code: str = "en") -> List[Dict[str, Any]]:
    """Fetches all active services with translations and verification status for the requested language."""
    db = get_db()
    query = """
        SELECT 
            s.id,
            s.slug,
            s.department,
            st.name,
            st.description,
            st.benefits,
            st.processing_time,
            st.official_fee,
            os.portal_name,
            os.source_url,
            os.verification_date,
            os.is_verified,
            (SELECT COUNT(*) FROM requirements r WHERE r.service_id = s.id) as total_requirements,
            (SELECT COUNT(*) FROM requirements r WHERE r.service_id = s.id AND r.is_mandatory = 1) as mandatory_requirements
        FROM services s
        JOIN service_translations st ON s.id = st.service_id AND st.lang_code = ?
        LEFT JOIN official_sources os ON s.id = os.service_id
        WHERE s.is_active = 1
        ORDER BY s.id ASC;
    """
    rows = db.execute(query, (lang_code,)).fetchall()
    return [dict(row) for row in rows]


def get_service_by_slug(slug: str, lang_code: str = "en") -> Optional[Dict[str, Any]]:
    """Fetches a single service by slug with its requirements in the requested language."""
    db = get_db()
    service_query = """
        SELECT 
            s.id,
            s.slug,
            s.department,
            st.name,
            st.description,
            st.benefits,
            st.processing_time,
            st.official_fee,
            os.portal_name,
            os.source_url,
            os.verification_date,
            os.is_verified,
            os.notes as source_notes
        FROM services s
        JOIN service_translations st ON s.id = st.service_id AND st.lang_code = ?
        LEFT JOIN official_sources os ON s.id = os.service_id
        WHERE s.slug = ? AND s.is_active = 1;
    """
    service_row = db.execute(service_query, (lang_code, slug)).fetchone()
    if not service_row:
        return None

    service_dict = dict(service_row)

    # Fetch requirements
    req_query = """
        SELECT 
            r.id,
            r.requirement_code,
            r.is_mandatory,
            r.document_type,
            r.order_seq,
            rt.title,
            rt.description,
            rt.help_text
        FROM requirements r
        JOIN requirement_translations rt ON r.id = rt.requirement_id AND rt.lang_code = ?
        WHERE r.service_id = ?
        ORDER BY r.order_seq ASC, r.id ASC;
    """
    req_rows = db.execute(req_query, (lang_code, service_dict["id"])).fetchall()
    service_dict["requirements"] = [dict(r) for r in req_rows]
    return service_dict
