from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
import re


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
    cluster_name = StringField(
        "Cluster name",
        validators=[Optional(), Length(max=64)],
        render_kw={"placeholder": "Defaults to the project name"},
    )
    group_id = SelectField("Project group", choices=[(0, "Ungrouped")], coerce=int, default=0, validators=[Optional()])
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
    hardware = SelectField(
        "Hardware",
        choices=[("", "Select hardware"), ("dell", "Dell"), ("cisco", "Cisco")],
        validators=[Optional()],
    )
    node_count = IntegerField("Expected node count", default=2, validators=[DataRequired(), NumberRange(min=1, max=64)])
    submit = SubmitField("Save project")

    def validate_hypervisor(self, field) -> None:
        if self.platform_type.data == "virtual" and not field.data:
            raise ValidationError("Select an hypervisor for a virtual project.")

    def validate_cluster_name(self, field) -> None:
        value = (field.data or "").strip()
        if not value:
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
            raise ValidationError("Use 1–64 letters, numbers, hyphens, or underscores; start with a letter or number.")

    def validate_hardware(self, field) -> None:
        if self.platform_type.data == "physical" and not field.data:
            raise ValidationError("Select the hardware vendor for a physical project.")

    def validate(self, extra_validators=None) -> bool:
        valid = super().validate(extra_validators)
        if self.platform_type.data == "virtual" and not self.hypervisor.data:
            self.hypervisor.errors.append("Select a hypervisor for a virtual project.")
            valid = False
        if self.platform_type.data == "physical" and not self.hardware.data:
            self.hardware.errors.append("Select the hardware vendor for a physical project.")
            valid = False
        return valid


class ProjectImportForm(FlaskForm):
    archive = FileField("ClusterWeaver project archive", validators=[FileRequired()])
    submit = SubmitField("Import project")


class ServerProjectImportForm(FlaskForm):
    archive_name = SelectField("Archive available on server", validators=[DataRequired()])
    submit = SubmitField("Import from server")


class ProjectDeleteForm(FlaskForm):
    submit = SubmitField("Delete")


class ProjectGroupForm(FlaskForm):
    name = StringField("Group name", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)], render_kw={"rows": 3})
    color = StringField("Identifying color", validators=[DataRequired(), Length(min=7, max=7)], render_kw={"type": "color"})
    submit = SubmitField("Save group")

    def validate_name(self, field) -> None:
        if not (field.data or "").strip():
            raise ValidationError("Enter a group name.")

    def validate_color(self, field) -> None:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", field.data or ""):
            raise ValidationError("Select a valid color.")
