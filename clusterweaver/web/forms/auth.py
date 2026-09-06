from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, Regexp


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=128)], render_kw={"autocomplete": "username", "autofocus": True})
    password = PasswordField("Password", validators=[DataRequired(), Length(max=256)], render_kw={"autocomplete": "current-password"})
    submit = SubmitField("Sign in")


class LogoutForm(FlaskForm):
    submit = SubmitField("Sign out")


ROLE_CHOICES = [("user", "User — read only"), ("clusteradmin", "Cluster admin"), ("administrator", "Administrator")]


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=256)])
    confirm_password = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Change password")


class ThemeForm(FlaskForm):
    theme = SelectField("Interface theme", choices=[("dark", "Soft dark grey — default"), ("light", "Light")], validators=[DataRequired()])
    submit = SubmitField("Save theme")


class UserCreateForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=128), Regexp(r"^[A-Za-z0-9_.-]+$", message="Use letters, numbers, dots, underscores, or hyphens.")])
    password = PasswordField("Initial password", validators=[DataRequired(), Length(min=12, max=256)])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password")])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Create user")


class UserUpdateForm(FlaskForm):
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    password = PasswordField("New password (optional)", validators=[Optional(), Length(min=12, max=256)])
    submit = SubmitField("Update")
