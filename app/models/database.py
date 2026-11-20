"""
SevaPath SQLite Database Layer & Migration System.

Provides:
- Schema creation with foreign-key enforcement.
- Safe, versioned, idempotent database migration mechanism.
- Anonymous citizen session management with SHA-256 token hashing.
- Citizen-specific requirement applicability and completion persistence.
- Service and requirement query helpers.
- Deterministic preparation dashboard calculations.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
from flask import g, current_app

from app.core.dfa_engine import ServiceDFA, Requirement

# Target schema definition for fresh databases
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citizen_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP DEFAULT NULL
);

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
    presentation_category TEXT NOT NULL DEFAULT 'listed_applicability_unconfirmed',
    is_active INTEGER NOT NULL DEFAULT 1,
    logical_group TEXT DEFAULT NULL,
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
    citizen_session_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (citizen_session_id) REFERENCES citizen_sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS session_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    requirement_id INTEGER NOT NULL,
    is_completed INTEGER DEFAULT 0,
    applicability TEXT NOT NULL DEFAULT 'undetermined' CHECK(applicability IN ('applicable', 'not_applicable', 'undetermined')),
    selected_alternative TEXT DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES preparation_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    UNIQUE (session_id, requirement_id)
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_services_slug ON services(slug);
CREATE INDEX IF NOT EXISTS idx_service_translations_lang ON service_translations(service_id, lang_code);
CREATE INDEX IF NOT EXISTS idx_requirements_service ON requirements(service_id);
CREATE INDEX IF NOT EXISTS idx_req_translations_lang ON requirement_translations(requirement_id, lang_code);
CREATE INDEX IF NOT EXISTS idx_citizen_sessions_hash ON citizen_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_prep_sessions_citizen ON preparation_sessions(citizen_session_id);
CREATE INDEX IF NOT EXISTS idx_session_items_applicability ON session_items(session_id, applicability);
"""


def get_db() -> sqlite3.Connection:
    """Returns an active SQLite database connection for the current Flask request context."""
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Closes the active database connection if open."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db_connection(db_path: str) -> sqlite3.Connection:
    """Helper to get a direct SQLite connection outside of Flask request context."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def run_migrations(db: sqlite3.Connection):
    """
    Executes idempotent, versioned database migrations.
    Safely upgrades existing databases to Phase 4 schema without deleting historical data.
    """
    cursor = db.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    applied = {row[0] for row in cursor.execute("SELECT version FROM schema_migrations;").fetchall()}

    # Migration 1: Phase 4 Citizen Sessions and Applicability Schema
    if 1 not in applied:
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            # 1. citizen_sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citizen_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_hash TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    revoked_at TIMESTAMP DEFAULT NULL
                );
            """)

            # 2. Add citizen_session_id to preparation_sessions if not present
            prep_cols = {row[1] for row in cursor.execute("PRAGMA table_info(preparation_sessions);").fetchall()}
            if "citizen_session_id" not in prep_cols:
                cursor.execute("""
                    ALTER TABLE preparation_sessions
                    ADD COLUMN citizen_session_id INTEGER DEFAULT NULL
                    REFERENCES citizen_sessions(id) ON DELETE SET NULL;
                """)

            # 3. Add presentation_category, is_active, logical_group to requirements if not present
            req_cols = {row[1] for row in cursor.execute("PRAGMA table_info(requirements);").fetchall()}
            if "presentation_category" not in req_cols:
                cursor.execute("ALTER TABLE requirements ADD COLUMN presentation_category TEXT NOT NULL DEFAULT 'legacy_unreviewed';")
            if "is_active" not in req_cols:
                cursor.execute("ALTER TABLE requirements ADD COLUMN is_active INTEGER NOT NULL DEFAULT 0;")
            if "logical_group" not in req_cols:
                cursor.execute("ALTER TABLE requirements ADD COLUMN logical_group TEXT DEFAULT NULL;")

            # 4. Add applicability and selected_alternative to session_items if not present
            item_cols = {row[1] for row in cursor.execute("PRAGMA table_info(session_items);").fetchall()}
            if "applicability" not in item_cols:
                cursor.execute("ALTER TABLE session_items ADD COLUMN applicability TEXT NOT NULL DEFAULT 'undetermined';")
            if "selected_alternative" not in item_cols:
                cursor.execute("ALTER TABLE session_items ADD COLUMN selected_alternative TEXT DEFAULT NULL;")

            # 5. Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_citizen_sessions_hash ON citizen_sessions(token_hash);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prep_sessions_citizen ON preparation_sessions(citizen_session_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_items_applicability ON session_items(session_id, applicability);")

            # 6. Record migration
            cursor.execute("INSERT INTO schema_migrations (version, name) VALUES (1, 'phase_4_citizen_sessions_and_applicability');")

            # 7. Verify foreign keys
            fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                raise RuntimeError(f"Foreign key integrity violation during migration: {fk_violations}")

            db.commit()
        except Exception as e:
            db.rollback()
            raise e


def init_db(app=None):
    """Initializes schema, executes migrations, and seeds initial services."""
    def _run(db):
        db.executescript(SCHEMA_SQL)
        run_migrations(db)
        from app.data.seeds import seed_initial_services
        seed_initial_services(db)
        db.commit()

    if app:
        with app.app_context():
            _run(get_db())
    else:
        _run(get_db())


# --- Citizen Session Database Helpers ---

def create_citizen_session(token_hash: str, expires_at: str) -> int:
    """Inserts a new anonymous citizen session storing only the SHA-256 token hash."""
    db = get_db()
    cur = db.execute(
        "INSERT INTO citizen_sessions (token_hash, expires_at) VALUES (?, ?)",
        (token_hash, expires_at)
    )
    db.commit()
    return cur.lastrowid


def get_citizen_session_by_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Retrieves an active, unrevoked citizen session by its token hash."""
    db = get_db()
    row = db.execute(
        "SELECT id, token_hash, created_at, last_seen_at, expires_at, revoked_at "
        "FROM citizen_sessions WHERE token_hash = ? AND revoked_at IS NULL",
        (token_hash,)
    ).fetchone()
    return dict(row) if row else None


def update_citizen_session_activity(citizen_id: int):
    """Updates the last_seen_at timestamp for an active citizen session."""
    db = get_db()
    db.execute(
        "UPDATE citizen_sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
        (citizen_id,)
    )
    db.commit()


def rotate_citizen_session_hash(
    citizen_id: int,
    new_token_hash: str,
    new_expires_at: str,
    old_token_hash: Optional[str] = None
) -> bool:
    """
    Transactionally rotates the token hash for an existing citizen session using compare-and-swap.
    If old_token_hash is provided, updates only if token_hash matches old_token_hash.
    Returns True if update succeeded, False if already rotated or invalid.
    """
    db = get_db()
    if old_token_hash is not None:
        cursor = db.execute(
            "UPDATE citizen_sessions SET token_hash = ?, expires_at = ?, last_seen_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND token_hash = ? AND revoked_at IS NULL",
            (new_token_hash, new_expires_at, citizen_id, old_token_hash)
        )
    else:
        cursor = db.execute(
            "UPDATE citizen_sessions SET token_hash = ?, expires_at = ?, last_seen_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND revoked_at IS NULL",
            (new_token_hash, new_expires_at, citizen_id)
        )
    db.commit()
    return cursor.rowcount > 0


def revoke_citizen_session_by_id(citizen_id: int):
    """Revokes a citizen session, marking it invalid for future requests."""
    db = get_db()
    db.execute(
        "UPDATE citizen_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
        (citizen_id,)
    )
    db.commit()


# --- Preparation Session Helpers ---

def get_or_create_preparation_session(citizen_session_id: int, service_id: int) -> Dict[str, Any]:
    """
    Finds or initializes a preparation session bound to the citizen's anonymous cookie identity.
    """
    db = get_db()
    row = db.execute(
        "SELECT id, session_token, service_id, citizen_session_id, created_at, updated_at "
        "FROM preparation_sessions WHERE citizen_session_id = ? AND service_id = ?",
        (citizen_session_id, service_id)
    ).fetchone()
    if row:
        return dict(row)

    # Generate internal UUID token to satisfy legacy NOT NULL UNIQUE constraint
    internal_token = uuid.uuid4().hex
    cur = db.execute(
        "INSERT INTO preparation_sessions (session_token, service_id, citizen_session_id) VALUES (?, ?, ?)",
        (internal_token, service_id, citizen_session_id)
    )
    db.commit()
    return {
        "id": cur.lastrowid,
        "session_token": internal_token,
        "service_id": service_id,
        "citizen_session_id": citizen_session_id
    }


def get_or_create_session(service_id: int, session_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Legacy helper preserved for backward compatibility.
    """
    db = get_db()
    if session_token:
        row = db.execute(
            "SELECT id, session_token, service_id FROM preparation_sessions WHERE session_token = ? AND service_id = ?",
            (session_token, service_id)
        ).fetchone()
        if row:
            return {"session_id": row["id"], "session_token": row["session_token"], "service_id": row["service_id"]}

    new_token = uuid.uuid4().hex
    cur = db.execute(
        "INSERT INTO preparation_sessions (session_token, service_id) VALUES (?, ?)",
        (new_token, service_id)
    )
    db.commit()
    return {"session_id": cur.lastrowid, "session_token": new_token, "service_id": service_id}


# --- Requirements and Progress Helpers ---

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
            (SELECT COUNT(*) FROM requirements r WHERE r.service_id = s.id AND r.is_active = 1) as total_requirements,
            (SELECT COUNT(*) FROM requirements r WHERE r.service_id = s.id AND r.is_active = 1 AND r.is_mandatory = 1) as mandatory_requirements
        FROM services s
        JOIN service_translations st ON s.id = st.service_id AND st.lang_code = ?
        LEFT JOIN official_sources os ON s.id = os.service_id
        WHERE s.is_active = 1
        ORDER BY s.id ASC;
    """
    rows = db.execute(query, (lang_code,)).fetchall()
    return [dict(r) for r in rows]


def get_service_by_slug(slug: str, lang_code: str = "en") -> Optional[Dict[str, Any]]:
    """Fetches full service details including official sources and active requirements."""
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
            os.notes
        FROM services s
        JOIN service_translations st ON s.id = st.service_id AND st.lang_code = ?
        LEFT JOIN official_sources os ON s.id = os.service_id
        WHERE s.slug = ? AND s.is_active = 1;
    """
    service_row = db.execute(service_query, (lang_code, slug)).fetchone()
    if not service_row:
        return None

    service_dict = dict(service_row)

    req_query = """
        SELECT
            r.id,
            r.requirement_code,
            r.is_mandatory,
            r.document_type,
            r.order_seq,
            r.presentation_category,
            r.is_active,
            r.logical_group,
            rt.title,
            rt.description,
            rt.help_text
        FROM requirements r
        JOIN requirement_translations rt ON r.id = rt.requirement_id AND rt.lang_code = ?
        WHERE r.service_id = ? AND r.is_active = 1
        ORDER BY r.order_seq ASC, r.id ASC;
    """
    req_rows = db.execute(req_query, (lang_code, service_dict["id"])).fetchall()
    service_dict["requirements"] = [dict(r) for r in req_rows]
    return service_dict


def get_service_requirements_with_citizen_state(
    service_id: int,
    session_id: int,
    lang_code: str = "en"
) -> List[Dict[str, Any]]:
    """
    Fetches active requirements combined with the citizen session's completion and applicability decisions.
    Initializes missing session_items rows as 'undetermined'.
    """
    db = get_db()

    # Ensure all active requirements exist in session_items
    db.execute("""
        INSERT OR IGNORE INTO session_items (session_id, requirement_id, is_completed, applicability)
        SELECT ?, id, 0, 'undetermined'
        FROM requirements
        WHERE service_id = ? AND is_active = 1;
    """, (session_id, service_id))
    db.commit()

    query = """
        SELECT
            r.id,
            r.requirement_code,
            r.is_mandatory,
            r.document_type,
            r.order_seq,
            r.presentation_category,
            r.logical_group,
            rt.title,
            rt.description,
            rt.help_text,
            COALESCE(si.is_completed, 0) as is_completed,
            COALESCE(si.applicability, 'undetermined') as applicability,
            si.selected_alternative
        FROM requirements r
        JOIN requirement_translations rt ON r.id = rt.requirement_id AND rt.lang_code = ?
        LEFT JOIN session_items si ON r.id = si.requirement_id AND si.session_id = ?
        WHERE r.service_id = ? AND r.is_active = 1
        ORDER BY r.order_seq ASC, r.id ASC;
    """
    rows = db.execute(query, (lang_code, session_id, service_id)).fetchall()
    return [dict(r) for r in rows]


def update_session_item_applicability(
    session_id: int,
    service_id: int,
    req_code: str,
    applicability: str
) -> Tuple[bool, Optional[str]]:
    """
    Updates the citizen's applicability decision for a requirement.
    If marked not_applicable, resets completion to 0.
    """
    if applicability not in ("applicable", "not_applicable", "undetermined"):
        return False, f"Invalid applicability decision '{applicability}'."

    db = get_db()

    req_row = db.execute(
        "SELECT id FROM requirements WHERE service_id = ? AND requirement_code = ? AND is_active = 1",
        (service_id, req_code)
    ).fetchone()
    if not req_row:
        return False, f"Active requirement '{req_code}' not found for this service."

    req_id = req_row["id"]
    completed_adjustment = 0 if applicability == "not_applicable" else None

    if completed_adjustment is not None:
        db.execute("""
            INSERT INTO session_items (session_id, requirement_id, applicability, is_completed, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, requirement_id) DO UPDATE SET
                applicability = excluded.applicability,
                is_completed = excluded.is_completed,
                updated_at = CURRENT_TIMESTAMP;
        """, (session_id, req_id, applicability, completed_adjustment))
    else:
        db.execute("""
            INSERT INTO session_items (session_id, requirement_id, applicability, is_completed, updated_at)
            VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, requirement_id) DO UPDATE SET
                applicability = excluded.applicability,
                updated_at = CURRENT_TIMESTAMP;
        """, (session_id, req_id, applicability))

    # Update preparation session timestamp
    db.execute("UPDATE preparation_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    db.commit()
    return True, None


def update_session_item_completion(
    session_id: int,
    service_id: int,
    req_code: str,
    is_completed: bool,
    selected_alternative: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Updates completion status of a requirement.
    """
    db = get_db()

    req_row = db.execute(
        "SELECT id FROM requirements WHERE service_id = ? AND requirement_code = ? AND is_active = 1",
        (service_id, req_code)
    ).fetchone()
    if not req_row:
        return False, f"Active requirement '{req_code}' not found for this service."

    req_id = req_row["id"]
    completed_val = 1 if is_completed else 0

    db.execute("""
        INSERT INTO session_items (session_id, requirement_id, is_completed, selected_alternative, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id, requirement_id) DO UPDATE SET
            is_completed = excluded.is_completed,
            selected_alternative = COALESCE(excluded.selected_alternative, session_items.selected_alternative),
            updated_at = CURRENT_TIMESTAMP;
    """, (session_id, req_id, completed_val, selected_alternative))

    db.execute("UPDATE preparation_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    db.commit()
    return True, None


def update_session_requirement(
    session_id: int,
    service_id: int,
    req_code: str,
    is_completed: bool
) -> Tuple[bool, Optional[str]]:
    """Legacy alias for backward compatibility."""
    return update_session_item_completion(session_id, service_id, req_code, is_completed)


def reset_service_preparation(session_id: int, service_id: int) -> bool:
    """
    Resets progress and applicability for a single service in this citizen's session.
    """
    db = get_db()
    db.execute("""
        UPDATE session_items
        SET is_completed = 0, applicability = 'undetermined', selected_alternative = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ?;
    """, (session_id,))
    db.execute("UPDATE preparation_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    db.commit()
    return True


def reset_session_progress(session_id: int, service_id: int) -> bool:
    """Legacy reset alias."""
    return reset_service_preparation(session_id, service_id)


def get_session_completed_keys(session_id: int) -> Set[str]:
    """Retrieves all requirement_codes marked completed for a given session."""
    db = get_db()
    rows = db.execute(
        """SELECT r.requirement_code
           FROM session_items si
           JOIN requirements r ON si.requirement_id = r.id
           WHERE si.session_id = ? AND si.is_completed = 1 AND r.is_active = 1""",
        (session_id,)
    ).fetchall()
    return {row["requirement_code"] for row in rows}


def build_service_dfa(
    slug: str,
    citizen_session_id: Optional[int] = None,
    lang_code: str = "en",
    active_conditions: Optional[Dict[str, bool]] = None
) -> Tuple[Optional[ServiceDFA], Optional[Dict[str, Any]]]:
    """
    Constructs a ServiceDFA instance with citizen applicability decisions.
    """
    service = get_service_by_slug(slug, lang_code=lang_code)
    if not service:
        return None, None

    citizen_applicability: Optional[Dict[str, str]] = None

    if citizen_session_id is not None:
        prep_sess = get_or_create_preparation_session(citizen_session_id, service["id"])
        session_id = prep_sess["id"]
        req_items = get_service_requirements_with_citizen_state(service["id"], session_id, lang_code=lang_code)

        citizen_applicability = {}
        requirements = []
        for r in req_items:
            req_code = r["requirement_code"]
            app_val = r["applicability"]
            citizen_applicability[req_code] = app_val

            req_obj = Requirement(
                key=req_code,
                name_en=r["title"],
                name_ta=r["title"],
                is_mandatory=bool(r["is_mandatory"]),
                description=r.get("description", ""),
                help_text=r.get("help_text", ""),
                presentation_category=r.get("presentation_category", "listed_applicability_unconfirmed"),
                logical_group=r.get("logical_group"),
                applicability=app_val,
                selected_alternative=r.get("selected_alternative")
            )
            requirements.append(req_obj)

        dfa = ServiceDFA(
            service_id=slug,
            requirements=requirements,
            active_conditions=active_conditions,
            citizen_applicability=citizen_applicability
        )
        return dfa, service
    else:
        # Fallback without citizen session
        requirements = []
        for r in service["requirements"]:
            req_obj = Requirement(
                key=r["requirement_code"],
                name_en=r["title"],
                name_ta=r["title"],
                is_mandatory=bool(r["is_mandatory"]),
                description=r.get("description", ""),
                help_text=r.get("help_text", ""),
                presentation_category=r.get("presentation_category", "listed_applicability_unconfirmed"),
                logical_group=r.get("logical_group")
            )
            requirements.append(req_obj)

        dfa = ServiceDFA(
            service_id=slug,
            requirements=requirements,
            active_conditions=active_conditions
        )
        return dfa, service


def get_citizen_dashboard_summary(citizen_session_id: int, lang_code: str = "en") -> List[Dict[str, Any]]:
    """
    Calculates progress and preparation status for all active services for the citizen dashboard.
    """
    services = get_services(lang_code=lang_code)
    summary_list = []

    for srv in services:
        slug = srv["slug"]
        dfa, srv_data = build_service_dfa(slug, citizen_session_id=citizen_session_id, lang_code=lang_code)
        if not dfa:
            continue

        prep_sess = get_or_create_preparation_session(citizen_session_id, srv["id"])
        completed_keys = get_session_completed_keys(prep_sess["id"])
        curr_state = dfa.requirements_to_state(completed_keys)
        progress = dfa.get_progress_summary(curr_state)

        srv_summary = dict(srv)
        srv_summary["progress"] = progress
        srv_summary["readiness_percentage"] = progress["readiness_percentage"]
        srv_summary["readiness_stage"] = progress["readiness_stage"]
        srv_summary["is_accepting"] = progress["is_accepting"]
        srv_summary["completed_count"] = progress["completed_count"]
        srv_summary["total_applicable"] = len(dfa.applicable_keys)
        srv_summary["undetermined_count"] = len(dfa.undetermined_keys)
        summary_list.append(srv_summary)

    return summary_list
