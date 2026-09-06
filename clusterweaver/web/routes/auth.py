from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from clusterweaver.web.forms.auth import LoginForm, LogoutForm
from clusterweaver.persistence import db
from clusterweaver.persistence.models import UserRecord


auth_bp = Blueprint("auth", __name__)
_DUMMY_PASSWORD_HASH = generate_password_hash("clusterweaver-invalid-password")


def _ensure_bootstrap_administrator() -> None:
    """Create the first administrator once, using deployment bootstrap credentials."""
    if db.session.scalar(select(UserRecord.id).limit(1)) is not None:
        return
    username = current_app.config.get("LOGIN_USERNAME", "").strip()
    password = current_app.config.get("LOGIN_PASSWORD", "")
    if not username or not password:
        return
    db.session.add(UserRecord(username=username, password_hash=generate_password_hash(password), role="administrator"))
    db.session.commit()


def _local_destination(candidate: str | None) -> str | None:
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return None
    return candidate


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    _ensure_bootstrap_administrator()
    if session.get("authenticated"):
        return redirect(url_for("projects.index"))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        user = db.session.scalar(select(UserRecord).where(UserRecord.username == username))
        password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        if check_password_hash(password_hash, form.password.data) and user:
            session.clear()
            session["authenticated"] = True
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(_local_destination(request.args.get("next")) or url_for("projects.index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html", form=form, credentials_configured=db.session.scalar(select(UserRecord.id).limit(1)) is not None)


@auth_bp.post("/logout")
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        return redirect(url_for("projects.index"))
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("auth.login"))
