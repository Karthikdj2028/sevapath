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


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration with in-memory or dedicated test database."""
    TESTING = True
    DEBUG = False
    DATABASE_PATH = os.path.join(BASE_DIR, "instance", "test_sevapath.sqlite")


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
