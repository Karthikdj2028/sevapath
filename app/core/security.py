"""
SevaPath Application Security & Anonymous Citizen Session Management.

Provides:
- Cryptographically secure 256-bit anonymous cookie session generation.
- SHA-256 hashed storage in SQLite (raw tokens are never stored in the database).
- Session-bound CSRF token generation and constant-time validation.
- Cookie rotation and invalidation mechanisms.
- HttpOnly, SameSite=Lax, and Secure cookie enforcement.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from flask import session, request, current_app

CITIZEN_COOKIE_NAME = "sevapath_sid"
SESSION_LIFETIME_DAYS = 14
ROTATION_THRESHOLD_DAYS = 1


def hash_token(raw_token: str) -> str:
    """Computes a non-reversible SHA-256 hex digest of a raw cookie token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    """Generates a cryptographically random, URL-safe 256-bit (32 bytes) token string."""
    return secrets.token_urlsafe(32)


def generate_csrf_token(citizen_session_id: Optional[int] = None) -> str:
    """Generates a cryptographically random, session-bound 32-byte hex CSRF token."""
    token = secrets.token_hex(32)
    session["csrf_token"] = token
    if citizen_session_id is not None:
        session["csrf_citizen_id"] = citizen_session_id
    return token


def get_csrf_token(citizen_session_id: Optional[int] = None) -> str:
    """Retrieves the active session-bound CSRF token, generating one if not yet present."""
    token = session.get("csrf_token")
    if not token or not isinstance(token, str):
        token = generate_csrf_token(citizen_session_id)
    elif citizen_session_id is not None and session.get("csrf_citizen_id") is None:
        session["csrf_citizen_id"] = citizen_session_id
    return token


def verify_csrf_token(submitted_token: Optional[str], citizen_session_id: Optional[int] = None) -> bool:
    """
    Validates submitted CSRF token against active session token in constant time.
    Also validates that the CSRF token belongs to the authenticated citizen identity.

    Returns:
        bool: True if submitted token matches session token, False otherwise.
    """
    if not submitted_token or not isinstance(submitted_token, str):
        return False

    session_token = session.get("csrf_token")
    if not session_token or not isinstance(session_token, str):
        return False

    # Validate binding to citizen session ID if provided
    if citizen_session_id is not None:
        bound_id = session.get("csrf_citizen_id")
        if bound_id is not None and bound_id != citizen_session_id:
            return False

    # Constant-time comparison to prevent timing side-channel attacks
    return hmac.compare_digest(session_token, submitted_token)


def authenticate_citizen_session(req=None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Authenticates a citizen session from incoming HttpOnly cookie for mutation requests.
    Strictly enforces presence of valid, active, non-expired, and non-revoked session.
    Does NOT create a new session if missing, invalid, or expired.

    Returns:
        Tuple[Optional[Dict[str, Any]], Optional[str]]:
        (citizen_session_dict, error_message)
    """
    if req is None:
        req = request

    from app.models.database import get_citizen_session_by_hash, update_citizen_session_activity

    raw_cookie = req.cookies.get(CITIZEN_COOKIE_NAME)
    if not raw_cookie or not isinstance(raw_cookie, str):
        return None, "Citizen session cookie is missing."

    token_hash = hash_token(raw_cookie)
    existing_session = get_citizen_session_by_hash(token_hash)
    if not existing_session:
        return None, "Invalid or revoked citizen session."

    if existing_session.get("revoked_at") is not None:
        return None, "Citizen session has been revoked."

    now = datetime.now(timezone.utc)
    expires_at_str = existing_session["expires_at"]
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return None, "Corrupted session expiration metadata."

    if expires_at <= now:
        return None, "Citizen session has expired."

    # Update activity timestamp
    update_citizen_session_activity(existing_session["id"])
    return existing_session, None


def rotate_citizen_session(raw_token: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Race-safe token rotation using compare-and-swap on SQLite token_hash.
    Atomically updates the token hash to the new hash.
    The old raw token is immediately invalidated for mutations.

    Returns:
        Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        (new_raw_token, updated_session_dict, error_message)
    """
    from app.models.database import get_citizen_session_by_hash, rotate_citizen_session_hash

    if not raw_token or not isinstance(raw_token, str):
        return None, None, "Invalid token provided for rotation."

    old_hash = hash_token(raw_token)
    existing_session = get_citizen_session_by_hash(old_hash)
    if not existing_session:
        return None, None, "Session not found or already rotated/revoked."

    now = datetime.now(timezone.utc)
    new_raw_token = generate_raw_token()
    new_hash = hash_token(new_raw_token)
    new_expires = (now + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()

    # Compare-and-swap: only succeeds if token_hash still equals old_hash
    success = rotate_citizen_session_hash(
        existing_session["id"],
        new_hash,
        new_expires,
        old_token_hash=old_hash
    )
    if not success:
        return None, None, "Concurrent rotation detected; old token invalidated."

    existing_session["token_hash"] = new_hash
    existing_session["expires_at"] = new_expires
    existing_session["last_seen_at"] = now.isoformat()
    return new_raw_token, existing_session, None


def resolve_citizen_session(req=None) -> Tuple[Dict[str, Any], Optional[str], bool]:
    """
    Resolves the active citizen session from the incoming HttpOnly cookie for safe/read requests.

    Returns:
        Tuple[Dict[str, Any], Optional[str], bool]:
        (citizen_session_dict, raw_token_to_set, is_new_or_rotated)
        - If existing valid session found: (session_dict, None, False)
        - If rotated: (session_dict, new_raw_token, True)
        - If missing/invalid/expired: creates a fresh isolated session and returns (new_session, new_token, True)
    """
    if req is None:
        req = request

    from app.models.database import (
        get_citizen_session_by_hash,
        create_citizen_session,
        update_citizen_session_activity,
        rotate_citizen_session_hash
    )

    raw_cookie = req.cookies.get(CITIZEN_COOKIE_NAME)
    now = datetime.now(timezone.utc)

    if raw_cookie and isinstance(raw_cookie, str):
        token_hash = hash_token(raw_cookie)
        existing_session = get_citizen_session_by_hash(token_hash)

        if existing_session and existing_session.get("revoked_at") is None:
            # Check expiration
            expires_at_str = existing_session["expires_at"]
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except Exception:
                expires_at = now - timedelta(seconds=1)

            if expires_at > now:
                # Valid active session: update activity timestamp
                update_citizen_session_activity(existing_session["id"])

                # Check for rotation threshold
                created_at_str = existing_session["created_at"]
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_days = (now - created_at).total_seconds() / 86400.0
                except Exception:
                    age_days = 0.0

                if age_days >= ROTATION_THRESHOLD_DAYS:
                    new_raw_token, updated_sess, err = rotate_citizen_session(raw_cookie)
                    if new_raw_token and updated_sess:
                        return updated_sess, new_raw_token, True
                    # If concurrent rotation occurred, look up active session
                    active_sess = get_citizen_session_by_hash(token_hash)
                    if active_sess:
                        return active_sess, None, False

                return existing_session, None, False

    # Create new isolated anonymous session
    new_raw_token = generate_raw_token()
    new_hash = hash_token(new_raw_token)
    new_expires = (now + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()
    new_id = create_citizen_session(new_hash, new_expires)

    new_session_dict = {
        "id": new_id,
        "token_hash": new_hash,
        "expires_at": new_expires,
        "created_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
    }
    return new_session_dict, new_raw_token, True


def set_citizen_cookie(response, raw_token: str):
    """Sets the secure anonymous citizen cookie on a Flask response object."""
    secure_flag = current_app.config.get("SESSION_COOKIE_SECURE", False)
    max_age = SESSION_LIFETIME_DAYS * 24 * 3600
    response.set_cookie(
        CITIZEN_COOKIE_NAME,
        raw_token,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=secure_flag,
        path="/"
    )


def clear_citizen_cookie(response):
    """Clears the citizen session cookie on a Flask response object."""
    response.set_cookie(
        CITIZEN_COOKIE_NAME,
        "",
        max_age=0,
        httponly=True,
        samesite="Lax",
        path="/"
    )
