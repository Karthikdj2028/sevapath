import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "sevapath-dev-insecure-secret-key-2026")
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH",
        os.path.join(BASE_DIR, "instance", "sevapath.sqlite")
    )
    DEFAULT_LANGUAGE = "en"
    SUPPORTED_LANGUAGES = ["en", "ta"]
    TESTING = False

    # Session & Cookie Security (OWASP aligned)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # Enabled in ProductionConfig for HTTPS

    # Request payload boundary protection (1 MB)
    MAX_CONTENT_LENGTH = 1024 * 1024  # 1,048,576 bytes

    # Reverse proxy middleware flag
    PROXY_FIX_ENABLED = False
    PROXY_FIX_HOPS = 1


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    PROXY_FIX_ENABLED = False


class TestingConfig(Config):
    """Testing configuration with in-memory or dedicated test database."""
    TESTING = True
    DEBUG = False
    DATABASE_PATH = os.path.join(BASE_DIR, "instance", "test_sevapath.sqlite")
    PROXY_FIX_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Strict HTTPS in production
    # In production, require SECRET_KEY strictly from environment (no insecure fallback)
    SECRET_KEY = None
    PROXY_FIX_ENABLED = True      # Enabled for single-hop trusted edge proxy
    PROXY_FIX_HOPS = 1            # Strictly 1 trusted proxy hop in Phase 5.1


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
