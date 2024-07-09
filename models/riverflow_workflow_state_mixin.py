from odoo import _, fields, models, api
import json


class RiverFlowWorkflowStateMixin(models.AbstractModel):
    _name = "riverflow.workflow.state.mixin"
    _description = "Mixin to support workflow state in any model"

    workflow_state_id = fields.Many2one(
        'riverflow.workflow.state', 'State',
        tracking=True, index=True, help='Current workflow state')
    from_transition_ids = fields.Many2many(
        'riverflow.workflow.transition',
        compute='_compute_from_transition_ids',
    )
    workflow_state_name = fields.Char(
        'State name', related='workflow_state_id.name', store=True, index=True)
    workflow_transition_buttons_json = fields.Char(
        'Actions', compute='_compute_workflow_transition_buttons_json', store=False)

    @api.depends('workflow_state_id', 'workflow_state_id.from_transition_ids')
    def _compute_from_transition_ids(self):
        for s in self:
            s.from_transition_ids = self.env['riverflow.workflow.transition'].search([
                ('from_state_id', '=', s.workflow_state_id.id),
            ])

    def _compute_workflow_transition_buttons_json(self):
        for record in self:
            # needs int, for json serialization
            record_id = 0 if isinstance(
                record.id, models.NewId) else int(record.id)

            transition_ids = record.from_transition_ids
            workflow_transition_buttons = {
                'text': record.workflow_state_name or '',
                'buttons': [],
                'record_id': record_id,
            }

            if transition_ids:
                for transition in transition_ids:
                    workflow_transition_buttons['buttons'].append({
                        'index': transition.sequence,
                        'caption': transition.name,
                        'help': transition.description,
                        'action': 'action_button_click',
                        # context is posted back to the server side action method
                        'context': {
                            'transition_id': transition.id,
                        }
                    })

            record.workflow_transition_buttons_json = json.dumps(
                workflow_transition_buttons)

    def action_button_click(self):
        transition_id = self.env.context.get('transition_id')
        transition = self.env['riverflow.workflow.transition'].browse(
            transition_id)

        if transition.action_context:
            action_context = json.loads(transition.action_context) or {}
        else:
            action_context = {}
        # action_context.update({
        #     'name_readonly': False,
        #     'latest_messages_invisible': False,
        #     'days_relative_to_project_invisible': False,
        # })
        action_context['service_ids'] = self.ids
        action_context['transition_id'] = transition_id

        # This is a workflow transition action, for now just one base wizard
        action = {
            'type': 'ir.actions.act_window',
            'name': transition.name,  # Dialog title
            'res_model': 'riverflow.service.wizard',
            'view_mode': 'form',
            # ' riverflow.view_service_transition_action_default_form'
            'views': [(self.env.ref(transition.action_id.odoo_view).id, "form")],
            'target': 'new',
            'context': action_context,
        }

        return action
