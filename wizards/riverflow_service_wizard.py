from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# base-class for all service wizards
# see AutomaticEntryWizard


class ServiceWizard(models.TransientModel):
    # todo: make this a generic transition wizard, make service wizard a subclass
    _name = 'riverflow.service.wizard'
    _description = 'Service Wizard'

    name = fields.Char('Service Name')
    service_ids = fields.Many2many('riverflow.service')
    new_remark = fields.Html('New Remark')
    days_relative_to_project = fields.Integer('Days relative to project')
    transition_id = fields.Many2one(
        'riverflow.workflow.transition', 'Transition')

    def action_save(self):
        for wizard in self:
            transition = wizard.transition_id
            for service in wizard.service_ids:
                # todo: check if the transition is allowed and if the service is in the right state
                service.workflow_state_id = transition.to_state_id

                if not self.env.context.get('name_readonly'):
                    service.name = self.name
                if not self.env.context.get('new_remark_invisible'):
                    if self.new_remark:
                        # post a message in the mail_message model linked to the service
                        self.env['mail.message'].create({
                            'body': self.new_remark,
                            'model': 'riverflow.service',
                            'res_id': service.id,
                            'message_type': 'comment',
                            # 'Note' subtype
                            'subtype_id': self.env.ref('mail.mt_note').id,
                        })
                if not self.env.context.get('days_relative_to_project_invisible'):
                    service.days_relative_to_project = self.days_relative_to_project

        action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        # Get the default service_ids from the action.context
        service_ids = self.env.context.get('service_ids')
        if not service_ids:
            raise UserError(_('No services selected'))

        services = self.env['riverflow.service'].browse(service_ids)
        # 6: replace the list of ids in the Many2many field
        defaultValues['service_ids'] = [(6, 0, services.ids)]

        if (len(services) == 1):
            service = services[0]
            defaultValues['name'] = service.name
            defaultValues['new_remark'] = ''
            defaultValues['days_relative_to_project'] = service['days_relative_to_project']

        defaultValues['transition_id'] = self.env.context.get('transition_id')

        return defaultValues
