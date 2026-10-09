from flask_wtf import FlaskForm
from wtforms import HiddenField, BooleanField
from wtforms.validators import AnyOf, DataRequired, Optional
from clusterweaver.core.services.cluster_operations import ACTIONS

class ClusterOperationForm(FlaskForm):
    action = HiddenField(validators=[DataRequired(), AnyOf(list(ACTIONS))])
    node_id = HiddenField(validators=[Optional()])
    confirm = BooleanField('I confirm this operation on the displayed cluster and nodes.')
