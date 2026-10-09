from flask_wtf import FlaskForm
from wtforms import FieldList, Form, FormField, HiddenField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

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
    mode = SelectField("Connection", choices=[("oem", "DELL OpenManage Enterprise"), ("ipmi", "DELL iDRAC / IPMI diretto")], default="oem")
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
