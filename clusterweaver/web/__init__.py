from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask

from config import Config
from clusterweaver.persistence import db


def create_app(config_object=Config, **overrides) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)
    app.config.update(overrides)
    Path(app.config["PROJECTS_ROOT"]).mkdir(parents=True, exist_ok=True)
    database_url = app.config["DATABASE_URL"]
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    @app.template_filter("local_datetime")
    def local_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")

    from clusterweaver.web.routes.projects import projects_bp

    app.register_blueprint(projects_bp)
    return app
