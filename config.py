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
    WTF_CSRF_ENABLED = True


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
