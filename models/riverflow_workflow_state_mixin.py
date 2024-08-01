from odoo import _, fields, models, api
import json
from odoo.addons.riverflow.models.riverflow_workflow_transition_mixin import RiverflowWorkflowTransitionMixin  # type: ignore


class RiverflowWorkflowStateMixin(RiverflowWorkflowTransitionMixin):
    _name = "riverflow.workflow.state.mixin"
    _description = "Mixin to support workflow state in any model"

    # initial workflow
    workflow_id = fields.Many2one(
        'riverflow.workflow',
        domain="[('model', '=', model)]",
        string='Workflow', tracking=True)

    workflow_state_id = fields.Many2one(
        'riverflow.workflow.state', 'Workflow State',
        tracking=True, index=True, help='Current workflow state')
    from_transition_ids = fields.Many2many(
        'riverflow.workflow.transition',
        compute='_compute_from_transition_ids',
    )

    current_workflow_name = fields.Char(
        'Workflow name', related='workflow_state_id.workflow_id.name', store=True, index=True)
    workflow_state_name = fields.Char(
        'State name', related='workflow_state_id.name', store=True, index=True)
    transition_buttons_json = fields.Text(
        'State', compute='_compute_transition_buttons_json', store=False)

    # = self._name, made accessible for use in the filter-domain of the workflow dropdown
    model = fields.Char(compute='_compute_model',
                        help="Model on which the workflow runs.")

    @api.model
    def default_get(self, fields_list):
        res = super(RiverflowWorkflowStateMixin, self).default_get(fields_list)
        res['model'] = self._name
        return res

    @api.model
    def _compute_model(self):
        for record in self:
            record.model = record._name

    @api.onchange('workflow_id', 'workflow_state_id')
    def on_change_workflow_id(self):
        for s in self:
            if s.workflow_id and not s.workflow_state_id:
                startStates = self.env['riverflow.workflow.state'].search([
                    ('workflow_id', '=', s.workflow_id.id),
                ], limit=1, order='sequence,name,id')
                if (len(startStates)):
                    s.workflow_state_id = startStates[0]

    @api.depends('workflow_state_id', 'workflow_state_id.from_transition_ids')
    def _compute_from_transition_ids(self):
        for s in self:
            if not s.workflow_state_id:
                s.from_transition_ids = []
            else:
                s.from_transition_ids = self.env['riverflow.workflow.transition'].search([
                    ('from_state_id', '=', s.workflow_state_id.id),
                ], order='sequence,id')

    def _compute_transition_buttons_json(self):
        for record in self:
            wf_state_text = record.current_workflow_name or ''
            if record.workflow_state_name:
                wf_state_text = ' | '.join(
                    [wf_state_text, record.workflow_state_name])

            # todo: store the icon so its not a lookup
            icon = record.workflow_state_id.workflow_id.icon or ''
            is_end_state = record.workflow_state_id.is_end_state == True

            workflow_transition_buttons = {
                'text': wf_state_text,
                'workflow_icon': icon,
                'is_end_state': is_end_state,
                # this is not a start transition, so we can refresh the underlying list/form view
                'reload_on_close': True,
                'buttons': [],
            }

            transition_ids = record.from_transition_ids
            if transition_ids:
                index = 0
                for transition in transition_ids:
                    # workaround, sometimes transition is a clone? in lookup tables or so
                    transition_id = transition.id.origin if isinstance(
                        record.id, models.NewId) else int(transition.id)

                    workflow_transition_buttons['buttons'].append({
                        'index': index,
                        'caption': transition.name,
                        'help': transition.description,
                        'action': 'action_button_click',
                        # context is posted back to the server side action method
                        'context': {
                            'transition_id': transition_id,
                        }
                    }
                    )
                    index += 1

            record.transition_buttons_json = json.dumps(
                workflow_transition_buttons)

    def action_button_click(self):
        transition_id = self.env.context.get('transition_id')
        transition = self.env['riverflow.workflow.transition'].browse(
            transition_id)
        return self._prepare_transition_action(transition)
