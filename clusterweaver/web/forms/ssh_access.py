from flask_wtf import FlaskForm
from wtforms import BooleanField, FieldList, Form, FormField, HiddenField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class NodeSSHAccessForm(Form):
    node_id = HiddenField(validators=[DataRequired()])
    hostname = StringField('Hostname', validators=[DataRequired()], render_kw={'readonly': True})
    password = PasswordField('Current root password for this node', validators=[Optional(), Length(max=1024)], render_kw={'autocomplete': 'new-password'})


class ProjectSSHAccessForm(FlaskForm):
    source_ip = StringField('ClusterWeaver source IP as seen by the nodes', validators=[Optional(), Length(max=45)])
    password = PasswordField('Current root password shared by the nodes (optional)', validators=[Optional(), Length(max=1024)], render_kw={'autocomplete': 'new-password'})
    nodes = FieldList(FormField(NodeSSHAccessForm), min_entries=0, max_entries=64)
    confirm = BooleanField('I confirm the public-key changes on the selected project nodes.')
    install = SubmitField('Install / resume and verify project key')
    verify = SubmitField('Verify key-only access')
    rotate = SubmitField('Rotate project key')
    cleanup = SubmitField('Revoke previous key')
