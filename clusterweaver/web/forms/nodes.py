from ipaddress import ip_address

from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from clusterweaver.core.validators import validate_ip_address, validate_ipv4_cidr


def valid_ip(_form, field) -> None:
    try:
        validate_ip_address(field.data.strip() if field.data else "")
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def valid_cidr(_form, field) -> None:
    try:
        validate_ipv4_cidr(field.data.strip() if field.data else "")
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


class NodeForm(FlaskForm):
    hostname = StringField("Hostname", validators=[DataRequired(), Length(max=253)])
    nodename = StringField("Cluster node name", validators=[DataRequired(), Length(max=253)])
    fqdn = StringField("FQDN", validators=[Optional(), Length(max=253)])
    site = StringField(
        "Site",
        validators=[Optional(), Length(max=120)],
        render_kw={"placeholder": "e.g. Roma, Datacenter-A, VMware-DC1"},
    )
    management_ip = StringField("Management IP / subnet", validators=[DataRequired(), Length(max=45), valid_cidr], render_kw={"placeholder": "e.g. 192.168.27.24/24"})
    management_gateway = StringField("Management gateway", validators=[DataRequired(), Length(max=45), valid_ip], render_kw={"placeholder": "e.g. 192.168.27.1"})
    cluster_ip = StringField("Cluster/private IP / subnet", validators=[Optional(), Length(max=45), valid_cidr], render_kw={"placeholder": "e.g. 192.168.28.24/24"})
    cluster_gateway = StringField("Cluster/private gateway (optional)", validators=[Optional(), Length(max=45), valid_ip], render_kw={"placeholder": "e.g. 192.168.28.1"})
    primary_interface = StringField(
        "Primary interface",
        validators=[DataRequired(), Length(max=64)],
        render_kw={"list": "network-interface-options", "placeholder": "e.g. ens160"},
    )
    secondary_interface = StringField(
        "Secondary interface",
        validators=[Optional(), Length(max=64)],
        render_kw={"list": "network-interface-options", "placeholder": "e.g. ens224"},
    )
    bootstrap_ip = StringField(
        "SSH bootstrap IP",
        validators=[Optional(), Length(max=45), valid_ip],
        render_kw={"placeholder": "Current DHCP address used for the first SSH connection"},
    )
    ssh_port = IntegerField("SSH port", default=22, validators=[DataRequired(), NumberRange(min=1, max=65535)])
    submit = SubmitField("Save node")

    def validate_management_gateway(self, field) -> None:
        if not self.management_ip.data or not field.data:
            return
        try:
            network = validate_ipv4_cidr(self.management_ip.data.strip()).network
            gateway = ip_address(field.data.strip())
        except ValueError:
            return
        if gateway not in network:
            raise ValidationError("Management gateway must belong to the management subnet.")

    def validate_cluster_gateway(self, field) -> None:
        if not field.data:
            return
        if not self.cluster_ip.data:
            raise ValidationError("Configure the cluster/private IP and subnet before its gateway.")
        try:
            network = validate_ipv4_cidr(self.cluster_ip.data.strip()).network
            gateway = ip_address(field.data.strip())
        except ValueError:
            return
        if gateway not in network:
            raise ValidationError("Cluster/private gateway must belong to the cluster/private subnet.")
