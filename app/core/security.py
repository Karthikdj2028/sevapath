"""
SevaPath Application Security & CSRF Protection Module.

Provides:
- Cryptographically secure, session-bound CSRF token generation and validation.
- Constant-time token comparison via hmac.compare_digest against timing attacks.
"""

import hmac
import secrets
from typing import Optional
from flask import session


def generate_csrf_token() -> str:
    """Generates a cryptographically random, session-bound 32-byte hex CSRF token."""
    token = secrets.token_hex(32)
    session["csrf_token"] = token
    return token


def get_csrf_token() -> str:
    """Retrieves the active session-bound CSRF token, generating one if not yet present."""
    token = session.get("csrf_token")
    if not token or not isinstance(token, str):
        token = generate_csrf_token()
    return token


def verify_csrf_token(submitted_token: Optional[str]) -> bool:
    """
    Validates submitted CSRF token against active session token in constant time.
    
    Returns:
        bool: True if submitted token matches session token, False otherwise.
    """
    if not submitted_token or not isinstance(submitted_token, str):
        return False

    session_token = session.get("csrf_token")
    if not session_token or not isinstance(session_token, str):
        return False

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(session_token, submitted_token)
