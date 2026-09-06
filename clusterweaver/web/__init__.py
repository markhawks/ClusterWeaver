from pathlib import Path
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from flask import Flask, abort, g, redirect, request, session, url_for

from config import Config
from clusterweaver.persistence import db
from clusterweaver.persistence.models import UserRecord
from clusterweaver.version import __version__


def create_app(config_object=Config, **overrides) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)
    app.config.update(overrides)
    Path(app.config["PROJECTS_ROOT"]).mkdir(parents=True, exist_ok=True)
    database_url = app.config["DATABASE_URL"]
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    @app.context_processor
    def application_metadata() -> dict:
        from clusterweaver.web.forms.auth import LogoutForm

        def package_version(name: str) -> str:
            try:
                return version(name)
            except PackageNotFoundError:
                return "N/A"

        return {
            "clusterweaver_version": __version__,
            "logout_form": LogoutForm(),
            "selected_theme": getattr(getattr(g, "current_user", None), "theme", app.config.get("DEFAULT_THEME", "dark")),
            "software_components": (
                ("Python", sys.version.split()[0]),
                ("Flask", package_version("Flask")),
                ("Werkzeug", package_version("Werkzeug")),
                ("SQLAlchemy", package_version("SQLAlchemy")),
                ("Alembic", package_version("alembic")),
                ("Paramiko", package_version("paramiko")),
                ("Gunicorn", package_version("gunicorn")),
                ("PyYAML", package_version("PyYAML")),
                ("Bootstrap", "5.3.8"),
            ),
        }

    @app.template_filter("local_datetime")
    def local_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")

    from clusterweaver.web.routes.auth import auth_bp
    from clusterweaver.web.routes.projects import projects_bp
    from clusterweaver.web.routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(settings_bp)

    @app.before_request
    def require_login():
        if app.config["LOGIN_DISABLED"]:
            g.current_user = SimpleNamespace(id=0, username="test", role="administrator", theme=app.config.get("DEFAULT_THEME", "dark"))
            return None
        if request.endpoint in {"auth.login", "static"}:
            return None
        if not session.get("authenticated"):
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        user = db.session.get(UserRecord, session.get("user_id"))
        if user is None:
            session.clear()
            return redirect(url_for("auth.login"))
        g.current_user = user
        session["username"], session["role"] = user.username, user.role
        if user.role == "user":
            read_only_endpoints = {
                "projects.index", "projects.detail", "projects.changelog",
                "projects.export_project",
                "projects.download_precheck", "projects.download_network_check",
                "projects.download_hosts_update", "projects.download_network_connectivity",
                "settings.configuration", "settings.change_password", "auth.logout",
            }
            allowed_posts = {"settings.change_password", "settings.change_theme", "auth.logout"}
            if request.endpoint not in read_only_endpoints or (request.method != "GET" and request.endpoint not in allowed_posts):
                abort(403)
        return None

    return app
