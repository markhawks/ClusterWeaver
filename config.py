from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("CLUSTERWEAVER_SECRET_KEY", "development-only-change-me")
    DATABASE_URL = os.environ.get(
        "CLUSTERWEAVER_DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'data' / 'clusterweaver.db'}",
    )
    PROJECTS_ROOT = Path(os.environ.get("CLUSTERWEAVER_PROJECTS_ROOT", BASE_DIR / "data" / "projects"))
    CHANGELOG_PATH = Path(os.environ.get("CLUSTERWEAVER_CHANGELOG_PATH", BASE_DIR / "CHANGELOG.md"))
    HOST = os.environ.get("CLUSTERWEAVER_HOST", "127.0.0.1")
    PORT = int(os.environ.get("CLUSTERWEAVER_PORT", "5000"))
    DEBUG = os.environ.get("CLUSTERWEAVER_DEBUG", "0").lower() in {"1", "true", "yes"}
    SSH_BOOTSTRAP_PASSWORD = os.environ.get("CLUSTERWEAVER_SSH_BOOTSTRAP_PASSWORD", "")
    LOGIN_USERNAME = os.environ.get("CLUSTERWEAVER_LOGIN_USERNAME", "admin")
    LOGIN_PASSWORD = os.environ.get("CLUSTERWEAVER_LOGIN_PASSWORD", "changeme")
    LOGIN_DISABLED = False
    DEFAULT_THEME = "dark"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True
    # Leave room for multipart framing around the service-level 8 MiB archive limit.
    MAX_CONTENT_LENGTH = 9 * 1024 * 1024


class TestConfig(Config):
    TESTING = True
    LOGIN_DISABLED = True
    WTF_CSRF_ENABLED = False
