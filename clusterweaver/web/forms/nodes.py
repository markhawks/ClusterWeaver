from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from clusterweaver.core.validators import validate_ip_address


def valid_ip(_form, field) -> None:
    try:
        validate_ip_address(field.data.strip() if field.data else "")
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


class NodeForm(FlaskForm):
    hostname = StringField("Hostname", validators=[DataRequired(), Length(max=253)])
    fqdn = StringField("FQDN", validators=[Optional(), Length(max=253)])
    site = StringField(
        "Site",
        validators=[Optional(), Length(max=120)],
        render_kw={"placeholder": "e.g. Roma, Datacenter-A, VMware-DC1"},
    )
    management_ip = StringField("Management IP", validators=[Optional(), Length(max=45), valid_ip])
    cluster_ip = StringField("Cluster/private IP", validators=[Optional(), Length(max=45), valid_ip])
    primary_interface = StringField(
        "Primary interface",
        validators=[Optional(), Length(max=64)],
        render_kw={"list": "network-interface-options", "placeholder": "e.g. ens160"},
    )
    secondary_interface = StringField(
        "Secondary interface",
        validators=[Optional(), Length(max=64)],
        render_kw={"list": "network-interface-options", "placeholder": "e.g. ens224"},
    )
    submit = SubmitField("Save node")
