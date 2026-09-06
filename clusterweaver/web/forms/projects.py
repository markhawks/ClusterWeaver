from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


MINOR_CHOICES = [(str(value), str(value)) for value in range(10)]


class ProjectForm(FlaskForm):
    name = StringField(
        "Project name",
        validators=[DataRequired(), Length(max=160)],
        render_kw={"list": "project-name-suggestions", "placeholder": "e.g. postgres-ha-prod"},
    )
    customer = StringField(
        "Customer / organization",
        validators=[DataRequired(), Length(max=160)],
        render_kw={"placeholder": "e.g. ACME, Infrastructure Team, Home Lab"},
    )
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=5000)],
        render_kw={"rows": 3, "placeholder": "e.g. Two-node PostgreSQL HA cluster for production services."},
    )
    rhel_major = SelectField(
        "RHEL major version",
        choices=[(7, "RHEL 7"), (9, "RHEL 9"), (10, "RHEL 10")],
        coerce=int,
        default=10,
        validators=[DataRequired()],
    )
    rhel_minor = SelectField("RHEL minor version", choices=MINOR_CHOICES, default="2", validators=[DataRequired()])
    platform_type = SelectField(
        "Platform", choices=[("physical", "Physical"), ("virtual", "Virtual")], default="virtual", validators=[DataRequired()]
    )
    hypervisor = SelectField(
        "Hypervisor",
        choices=[("", "Select hypervisor"), ("vmware", "VMware"), ("kvm", "KVM"), ("proxmox", "Proxmox")],
        default="kvm",
        validators=[Optional()],
    )
    node_count = IntegerField("Expected node count", default=2, validators=[DataRequired(), NumberRange(min=1, max=64)])
    submit = SubmitField("Save project")

    def validate_hypervisor(self, field) -> None:
        if self.platform_type.data == "virtual" and not field.data:
            raise ValidationError("Select an hypervisor for a virtual project.")


class ProjectImportForm(FlaskForm):
    archive = FileField("ClusterWeaver project archive", validators=[FileRequired()])
    submit = SubmitField("Import project")
