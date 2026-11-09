from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, FieldList, Form, FormField, HiddenField, PasswordField, RadioField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from clusterweaver.core.services.stonith import validate_oem_endpoint


class DellProfileForm(Form):
    node_id = HiddenField(validators=[DataRequired()])
    hostname = StringField("Hostname", validators=[DataRequired(), Length(max=253)], render_kw={"readonly": True})
    profile_name = StringField("DELL profile name in OEM", validators=[Optional(), Length(max=160)])
    controller_endpoint = StringField("iDRAC IP address or hostname", validators=[Optional(), Length(max=253)])
    resource_name = StringField("STONITH resource name", validators=[Optional(), Length(max=160)])
    username = StringField("Userid", validators=[DataRequired(), Length(max=128)])
    password = PasswordField("OEM password", validators=[Optional(), Length(max=1024)], render_kw={"autocomplete": "new-password"})


class StonithProfilesForm(FlaskForm):
    hardware = SelectField("Hardware", choices=[("dell", "DELL")], default="dell", validators=[DataRequired()])
    mode = RadioField("Fencing connection", choices=[("ipmi", "Single iDRAC per node / IPMI"), ("oem", "DELL OEM profiles")], default="ipmi", validators=[DataRequired()])
    endpoint = StringField("OEM IP address or hostname", validators=[Length(max=253)], render_kw={"placeholder": "e.g. 10.0.0.50 or ome.example.com"})
    profiles = FieldList(FormField(DellProfileForm), min_entries=0, max_entries=64)
    save = SubmitField("Save profiles")
    verify = SubmitField("Save and verify OEM profiles")

    def validate_endpoint(self, field) -> None:
        if self.mode.data != "oem":
            return
        try:
            validate_oem_endpoint((field.data or "").strip())
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class FenceAgentsCheckForm(FlaskForm):
    password = PasswordField("Root SSH password override (optional with project key)", validators=[Optional(), Length(max=1024)], render_kw={"autocomplete": "new-password"})
    check = SubmitField("Check fence agents on cluster nodes")


class FencingCreateForm(FlaskForm):
    power_wait = IntegerField('Power wait (seconds)', default=4, validators=[NumberRange(min=0,max=300)])
    configure_monitor = BooleanField('Set explicit monitor settings')
    monitor_interval = IntegerField('Monitor interval (seconds)', default=60, validators=[Optional(),NumberRange(min=1,max=86400)])
    monitor_timeout = IntegerField('Monitor timeout (seconds)', default=60, validators=[Optional(),NumberRange(min=1,max=600)])
    failure_timeout = IntegerField('Failure timeout (seconds, optional)', validators=[Optional(),NumberRange(min=0,max=86400)])
    disabled = BooleanField('Create new devices disabled')
    confirm = BooleanField('I confirm creation of the displayed fencing resources in this cluster.', validators=[DataRequired()])
    preview = SubmitField('Update command preview')
    create = SubmitField('Create fencing devices')


class FencingVerifyForm(FlaskForm):
    verify = SubmitField('Verify fencing configuration')
