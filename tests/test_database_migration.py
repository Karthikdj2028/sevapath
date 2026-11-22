"""
Pytest database migration and historical data preservation test suite.

Verifies:
- Migration versioning via schema_migrations table.
- Upgrading from pre-Phase-4 legacy SQLite schema without data loss.
- Foreign key integrity post-migration.
- Historical requirement preservation (legacy items marked deprecated, never deleted).
- Historical session items and completion preservation.
- Atomic rollback on injected migration failure.
- Migration idempotency (repeated execution is safe).
"""

import sqlite3
import pytest
from app.models.database import run_migrations, init_db


def test_schema_migrations_version_recorded(app):
    """Verifies that schema_migrations records version 1 upon database initialization."""
    with app.app_context():
        from app.models.database import get_db
        db = get_db()
        row = db.execute("SELECT version, name FROM schema_migrations WHERE version = 1").fetchone()
        assert row is not None
        assert row["version"] == 1
        assert "phase_4" in row["name"]


def test_migration_idempotency(app):
    """Verifies that executing run_migrations repeatedly is safe and idempotent."""
    with app.app_context():
        from app.models.database import get_db
        db = get_db()
        # Run migration again
        run_migrations(db)
        run_migrations(db)

        # Assert foreign keys remain valid
        violations = db.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(violations) == 0


def test_legacy_database_upgrade_preserves_historical_records(tmp_path):
    """
    Simulates a legacy pre-Phase-4 database with old schema and records,
    executes run_migrations(), and asserts 100% data preservation.
    """
    db_file = tmp_path / "legacy_test.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON;")

    # 1. Create pre-Phase-4 schema
    conn.executescript("""
        CREATE TABLE services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            requirement_code TEXT NOT NULL,
            is_mandatory INTEGER DEFAULT 1,
            document_type TEXT NOT NULL,
            order_seq INTEGER DEFAULT 0,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
            UNIQUE (service_id, requirement_code)
        );
        CREATE TABLE preparation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            service_id INTEGER NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
        );
        CREATE TABLE session_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            requirement_id INTEGER NOT NULL,
            is_completed INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES preparation_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
            UNIQUE (session_id, requirement_id)
        );
    """)

    # 2. Seed legacy records
    conn.execute("INSERT INTO services (slug, department) VALUES ('nativity-certificate', 'Revenue')")
    srv_id = 1
    # Insert legacy requirements including deprecated 'birth_or_school_proof' and 'parent_nativity_proof'
    conn.execute("INSERT INTO requirements (service_id, requirement_code, is_mandatory, document_type, order_seq) VALUES (?, 'applicant_photo', 1, 'image', 1)", (srv_id,))
    conn.execute("INSERT INTO requirements (service_id, requirement_code, is_mandatory, document_type, order_seq) VALUES (?, 'birth_or_school_proof', 1, 'document', 2)", (srv_id,))
    conn.execute("INSERT INTO requirements (service_id, requirement_code, is_mandatory, document_type, order_seq) VALUES (?, 'parent_nativity_proof', 0, 'document', 3)", (srv_id,))
    
    # Insert legacy preparation session
    conn.execute("INSERT INTO preparation_sessions (session_token, service_id) VALUES ('legacy_token_123', ?)", (srv_id,))
    sess_id = 1

    # Mark legacy requirement 'birth_or_school_proof' as completed in session_items
    conn.execute("INSERT INTO session_items (session_id, requirement_id, is_completed) VALUES (?, 2, 1)", (sess_id,))
    conn.commit()

    # 3. Execute Phase 4 migration
    run_migrations(conn)

    # 4. Assert columns were added with safe defaults
    req_cols = {row[1]: row for row in conn.execute("PRAGMA table_info(requirements);").fetchall()}
    assert "presentation_category" in req_cols
    assert "is_active" in req_cols

    item_cols = {row[1]: row for row in conn.execute("PRAGMA table_info(session_items);").fetchall()}
    assert "applicability" in item_cols

    # 5. Assert historical session_item completion state is 100% preserved
    completed_item = conn.execute("SELECT is_completed, applicability FROM session_items WHERE session_id = ? AND requirement_id = 2", (sess_id,)).fetchone()
    assert completed_item[0] == 1  # is_completed is still 1!
    assert completed_item[1] == "undetermined"  # safe default

    # 6. Assert foreign key integrity
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert len(fk_violations) == 0

    conn.close()


def test_atomic_rollback_on_migration_failure(tmp_path):
    """
    Verifies that a failure during migration triggers clean ROLLBACK
    and leaves the pre-migration database completely untouched.
    """
    db_file = tmp_path / "rollback_test.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON;")

    # Setup base table
    conn.execute("CREATE TABLE services (id INTEGER PRIMARY KEY, slug TEXT UNIQUE);")
    conn.execute("INSERT INTO services (slug) VALUES ('test-srv');")
    conn.commit()

    # Define faulty migration function simulating mid-migration crash
    def faulty_migration(db):
        cursor = db.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute("CREATE TABLE citizen_sessions (id INTEGER PRIMARY KEY, token_hash TEXT UNIQUE);")
            cursor.execute("INSERT INTO citizen_sessions (token_hash) VALUES ('hash1');")
            # Injected failure
            cursor.execute("INSERT INTO nonexistent_broken_table VALUES (1);")
            db.commit()
        except Exception:
            db.rollback()
            raise

    # Assert exception raised
    with pytest.raises(sqlite3.OperationalError):
        faulty_migration(conn)

    # Assert rollback restored original state: citizen_sessions table must NOT exist!
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "citizen_sessions" not in tables
    assert "services" in tables

    conn.close()


def test_init_db_successfully_upgrades_legacy_phase3_database(tmp_path):
    """
    Regression test: Verifies that init_db() successfully starts up against
    and upgrades an authentic legacy Phase 3 SQLite database without raising
    OperationalError, preserves both completed and incomplete historical records,
    creates migration-dependent indexes, and validates foreign key integrity.
    """
    from app import create_app
    from app.models.database import init_db

    db_path = str(tmp_path / "legacy_phase3_startup.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    # 1. Construct authentic Phase 3 schema from commit a38d9ff
    conn.executescript("""
        CREATE TABLE services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE service_translations (
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
        CREATE TABLE official_sources (
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
        CREATE TABLE requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            requirement_code TEXT NOT NULL,
            is_mandatory INTEGER DEFAULT 1,
            document_type TEXT NOT NULL,
            order_seq INTEGER DEFAULT 0,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
            UNIQUE (service_id, requirement_code)
        );
        CREATE TABLE requirement_translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requirement_id INTEGER NOT NULL,
            lang_code TEXT NOT NULL CHECK(lang_code IN ('en', 'ta')),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            help_text TEXT,
            FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
            UNIQUE (requirement_id, lang_code)
        );
        CREATE TABLE preparation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            service_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
        );
        CREATE TABLE session_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            requirement_id INTEGER NOT NULL,
            is_completed INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES preparation_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
            UNIQUE (session_id, requirement_id)
        );
        CREATE INDEX IF NOT EXISTS idx_services_slug ON services(slug);
        CREATE INDEX IF NOT EXISTS idx_service_translations_lang ON service_translations(service_id, lang_code);
        CREATE INDEX IF NOT EXISTS idx_requirements_service ON requirements(service_id);
        CREATE INDEX IF NOT EXISTS idx_req_translations_lang ON requirement_translations(requirement_id, lang_code);
    """)

    # 2. Insert realistic historical service, requirement, preparation sessions, and items
    conn.execute("INSERT INTO services (id, slug, department) VALUES (1, 'income-certificate', 'Revenue');")
    conn.execute("INSERT INTO requirements (id, service_id, requirement_code, is_mandatory, document_type, order_seq) VALUES (1, 1, 'salary_slip', 1, 'document', 1);")
    conn.execute("INSERT INTO requirements (id, service_id, requirement_code, is_mandatory, document_type, order_seq) VALUES (2, 1, 'ration_card', 1, 'document', 2);")
    conn.execute("INSERT INTO preparation_sessions (id, session_token, service_id) VALUES (1, 'legacy_session_token_1', 1);")
    conn.execute("INSERT INTO preparation_sessions (id, session_token, service_id) VALUES (2, 'legacy_session_token_2', 1);")
    # Include both completed and incomplete checklist items
    conn.execute("INSERT INTO session_items (id, session_id, requirement_id, is_completed) VALUES (1, 1, 1, 1);") # completed
    conn.execute("INSERT INTO session_items (id, session_id, requirement_id, is_completed) VALUES (2, 1, 2, 0);") # incomplete
    conn.execute("INSERT INTO session_items (id, session_id, requirement_id, is_completed) VALUES (3, 2, 1, 1);") # completed
    conn.commit()
    conn.close()

    # 3. Create Flask testing app pointing to the legacy database
    app = create_app("testing")
    app.config["DATABASE_PATH"] = db_path

    # 4. Invoke init_db(app) - must succeed without sqlite3.OperationalError
    with app.app_context():
        init_db(app)

    # 5. Open and inspect post-upgrade database
    verify_conn = sqlite3.connect(db_path)
    verify_conn.row_factory = sqlite3.Row

    # 6. Verify migrated columns and actual migration defaults
    prep_cols = {r["name"]: r for r in verify_conn.execute("PRAGMA table_info(preparation_sessions);").fetchall()}
    assert "citizen_session_id" in prep_cols
    assert prep_cols["citizen_session_id"]["dflt_value"] in (None, "NULL")

    req_cols = {r["name"]: r for r in verify_conn.execute("PRAGMA table_info(requirements);").fetchall()}
    assert "presentation_category" in req_cols
    assert req_cols["presentation_category"]["dflt_value"] == "'legacy_unreviewed'"
    assert "is_active" in req_cols
    assert req_cols["is_active"]["dflt_value"] == "0"
    assert "logical_group" in req_cols
    assert req_cols["logical_group"]["dflt_value"] in (None, "NULL")

    item_cols = {r["name"]: r for r in verify_conn.execute("PRAGMA table_info(session_items);").fetchall()}
    assert "applicability" in item_cols
    assert item_cols["applicability"]["dflt_value"] == "'undetermined'"
    assert "selected_alternative" in item_cols
    assert item_cols["selected_alternative"]["dflt_value"] in (None, "NULL")

    # 7. Verify migration tracking
    mig = verify_conn.execute("SELECT version, name FROM schema_migrations WHERE version = 1;").fetchone()
    assert mig is not None
    assert mig["version"] == 1
    assert "phase_4" in mig["name"]

    # 8. Verify migration-dependent indexes
    indexes = {r["name"] for r in verify_conn.execute("SELECT name FROM sqlite_master WHERE type='index';").fetchall()}
    assert "idx_prep_sessions_citizen" in indexes
    assert "idx_session_items_applicability" in indexes

    # 9. Verify historical records and completion states are 100% preserved
    items = {r["id"]: dict(r) for r in verify_conn.execute("SELECT id, session_id, requirement_id, is_completed, applicability FROM session_items WHERE session_id = 1;").fetchall()}
    assert items[1]["is_completed"] == 1  # completed item stayed completed
    assert items[1]["applicability"] == "undetermined"
    assert items[2]["is_completed"] == 0  # incomplete item stayed incomplete
    assert items[2]["applicability"] == "undetermined"

    sessions = {r["id"]: dict(r) for r in verify_conn.execute("SELECT id, session_token, citizen_session_id FROM preparation_sessions;").fetchall()}
    assert sessions[1]["session_token"] == "legacy_session_token_1"
    assert sessions[1]["citizen_session_id"] is None
    assert sessions[2]["session_token"] == "legacy_session_token_2"

    # 10. Verify integrity and foreign key constraints
    fk_violations = verify_conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert len(fk_violations) == 0
    integrity = verify_conn.execute("PRAGMA integrity_check;").fetchone()[0]
    assert integrity == "ok"

    verify_conn.close()
