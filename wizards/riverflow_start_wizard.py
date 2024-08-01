from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
from odoo.addons.riverflow.models.riverflow_workflow_transition_mixin import RiverflowWorkflowTransitionMixin


class StartWizard(RiverflowWorkflowTransitionMixin):
    _name = 'riverflow.start.wizard'
    _description = 'Base Start Transition Wizard'

    def _default_start_transition_ids(self):
        domain = [
            ('from_state_id', '=', False),
            ('model', '=', self._workflow_model)
        ]
        return self.env['riverflow.workflow.transition'].search(domain, order='sequence,id')

    start_transition_ids = fields.Many2many(
        'riverflow.workflow.transition', default=_default_start_transition_ids)

    transition_buttons_json = fields.Text(
        'Start Transitions', compute='_compute_transition_buttons_json', store=False)

    @api.depends('start_transition_ids')
    def _compute_transition_buttons_json(self):
        for wizard in self:
            workflow_transition_buttons = {
                'text': '',
                'workflow_icon': '',
                'is_end_state': False,
                'reload_on_close': False,
                'buttons': [],
            }

            for index, transition in enumerate(wizard.start_transition_ids):
                transition_id = transition.id.origin if isinstance(
                    wizard.id, models.NewId) else int(transition.id)

                workflow_transition_buttons['buttons'].append({
                    'index': index,
                    'caption': transition.name,
                    'help': transition.description,
                    'action': 'action_start_transition',
                    'context': {
                        'transition_id': transition_id,
                    }
                })

            wizard.transition_buttons_json = json.dumps(
                workflow_transition_buttons)

    def action_start_transition(self):
        self.ensure_one()
        transition_id = self.env.context.get('transition_id')
        transition = self.env['riverflow.workflow.transition'].browse(
            transition_id)

        if not transition:
            raise UserError(_("No transition selected."))

        return self._prepare_transition_action(transition)
