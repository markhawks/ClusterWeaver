from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from clusterweaver.persistence import db
from clusterweaver.persistence.models import UserRecord
from clusterweaver.web.forms.auth import LogoutForm, PasswordChangeForm, ThemeForm, UserCreateForm, UserUpdateForm


settings_bp = Blueprint("settings", __name__, url_prefix="/configuration")


def administrator_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if not g.current_user or g.current_user.role != "administrator":
            abort(403)
        return view(*args, **kwargs)
    return protected


@settings_bp.get("")
def configuration():
    users = db.session.scalars(select(UserRecord).order_by(UserRecord.username)).all() if g.current_user.role == "administrator" else []
    update_forms = {}
    for user in users:
        form = UserUpdateForm(prefix=f"user-{user.id}")
        form.role.data = user.role
        update_forms[user.id] = form
    theme_form = ThemeForm(prefix="theme")
    theme_form.theme.data = g.current_user.theme
    return render_template(
        "settings/configuration.html",
        password_form=PasswordChangeForm(prefix="password"),
        create_form=UserCreateForm(prefix="create"),
        update_forms=update_forms,
        delete_forms={user.id: LogoutForm(prefix=f"delete-{user.id}") for user in users},
        users=users,
        theme_form=theme_form,
    )


@settings_bp.post("/theme")
def change_theme():
    form = ThemeForm(prefix="theme")
    if not form.validate_on_submit():
        flash("Select a valid interface theme.", "danger")
        return redirect(url_for("settings.configuration"))
    g.current_user.theme = form.theme.data
    g.current_user.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("Interface theme updated.", "success")
    return redirect(url_for("settings.configuration"))


@settings_bp.post("/password")
def change_password():
    form = PasswordChangeForm(prefix="password")
    if form.validate_on_submit() and check_password_hash(g.current_user.password_hash, form.current_password.data):
        changed_at = datetime.now(timezone.utc)
        g.current_user.password_hash = generate_password_hash(form.new_password.data)
        g.current_user.password_changed_at = changed_at
        g.current_user.updated_at = changed_at
        db.session.commit()
        flash("Password changed.", "success")
    else:
        if not form.current_password.errors:
            form.current_password.errors.append("Current password is incorrect.")
        flash("The password was not changed. Check the entered values.", "danger")
        return redirect(url_for("settings.configuration"))
    return redirect(url_for("settings.configuration"))


@settings_bp.post("/users")
@administrator_required
def create_user():
    form = UserCreateForm(prefix="create")
    if form.validate_on_submit():
        user = UserRecord(username=form.username.data.strip(), password_hash=generate_password_hash(form.password.data), role=form.role.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That username already exists.", "danger")
        else:
            flash(f"User {user.username} created.", "success")
    else:
        flash("Check the new user fields.", "danger")
    return redirect(url_for("settings.configuration"))


@settings_bp.post("/users/<int:user_id>")
@administrator_required
def update_user(user_id: int):
    user = db.session.get(UserRecord, user_id)
    if user is None:
        abort(404)
    form = UserUpdateForm(prefix=f"user-{user.id}")
    if form.validate_on_submit():
        if user.id == g.current_user.id and form.role.data != "administrator":
            flash("You cannot remove your own administrator role.", "danger")
        else:
            user.role = form.role.data
            if form.password.data:
                user.password_hash = generate_password_hash(form.password.data)
                user.password_changed_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            flash(f"User {user.username} updated.", "success")
    else:
        flash("Check the user update fields.", "danger")
    return redirect(url_for("settings.configuration"))


@settings_bp.post("/users/<int:user_id>/delete")
@administrator_required
def delete_user(user_id: int):
    form = LogoutForm(prefix=f"delete-{user_id}")
    if not form.validate_on_submit():
        abort(400)
    user = db.session.get(UserRecord, user_id)
    if user is None:
        abort(404)
    if user.id == g.current_user.id:
        flash("You cannot delete your own account.", "danger")
    elif user.role == "administrator" and db.session.scalar(select(func.count()).select_from(UserRecord).where(UserRecord.role == "administrator")) <= 1:
        flash("The last administrator cannot be deleted.", "danger")
    else:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        flash(f"User {username} deleted.", "success")
    return redirect(url_for("settings.configuration"))
