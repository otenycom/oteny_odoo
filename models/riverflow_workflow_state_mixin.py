from odoo import _, fields, models


class RiverFlowWorkflowStateMixin(models.AbstractModel):
    _name = "riverflow.workflow.state.mixin"
    _description = "Mixin to support workflow state in any model"

    workflow_state_id = fields.Many2one(
        'riverflow.workflow.state', 'State', tracking=True, index=True, help='Current workflow state')

    # def _get_transition_actions(self):
