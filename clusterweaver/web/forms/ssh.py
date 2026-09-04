from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional


class SSHDiscoveryForm(FlaskForm):
    password = PasswordField("Initial root password override", validators=[Optional()], render_kw={"autocomplete": "off"})
    submit = SubmitField("Run read-only discovery")


class SSHKeyBootstrapForm(FlaskForm):
    password = PasswordField("Initial root password override", validators=[Optional()], render_kw={"autocomplete": "off"})
    confirm = BooleanField("I understand this creates root SSH keys and updates authorized_keys on every node.", validators=[DataRequired()])
    submit = SubmitField("Create peer SSH trust")


class NetworkApplyForm(FlaskForm):
    node_id = SelectField("Node", coerce=int, validators=[DataRequired()])
    password = PasswordField("Initial root password override", validators=[Optional()], render_kw={"autocomplete": "off"})
    confirm = BooleanField("I understand that this changes the selected node's active network configuration.", validators=[DataRequired()])
    submit = SubmitField("Apply network configuration")


class PrecheckRunForm(FlaskForm):
    password = PasswordField("Root password override", validators=[Optional()], render_kw={"autocomplete": "off"})
    submit = SubmitField("Run on all nodes")


class NetworkCheckRunForm(FlaskForm):
    password = PasswordField("Root password override", validators=[Optional()], render_kw={"autocomplete": "off"})
    submit = SubmitField("Run on all nodes")
