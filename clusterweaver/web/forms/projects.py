from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


MINOR_CHOICES = [(str(value), str(value)) for value in range(10)]


class ProjectForm(FlaskForm):
    name = StringField("Project name", validators=[DataRequired(), Length(max=160)])
    customer = StringField("Customer / organization", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=5000)])
    rhel_major = SelectField(
        "RHEL major version",
        choices=[(7, "RHEL 7"), (9, "RHEL 9"), (10, "RHEL 10")],
        coerce=int,
        validators=[DataRequired()],
    )
    rhel_minor = SelectField("RHEL minor version", choices=MINOR_CHOICES, default="9", validators=[DataRequired()])
    platform_type = SelectField(
        "Platform", choices=[("physical", "Physical"), ("virtual", "Virtual")], validators=[DataRequired()]
    )
    node_count = IntegerField("Expected node count", validators=[DataRequired(), NumberRange(min=1, max=64)])
    submit = SubmitField("Save project")
