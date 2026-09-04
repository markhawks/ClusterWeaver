from pathlib import Path
import pytest

from clusterweaver import create_app
from config import TestConfig
from clusterweaver.persistence.database import Base, db


@pytest.fixture()
def app(tmp_path: Path):
    application = create_app(
        TestConfig,
        SECRET_KEY="test-secret",
        DATABASE_URL=f"sqlite:///{tmp_path / 'test.db'}",
        PROJECTS_ROOT=tmp_path / "projects",
    )
    with application.app_context():
        Base.metadata.create_all(db.engine)
        yield application
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()

