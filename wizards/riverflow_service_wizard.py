from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# base-class for all service wizards
# see AutomaticEntryWizard
class ServiceWizard(models.TransientModel):
    _name = 'riverflow.service.wizard'
    _description = 'Service Wizard'

    name = fields.Char('Service Name')
    service_ids = fields.Many2many('riverflow.service')
    internal_remarks = fields.Text('Internal Remarks')
    days_relative_to_project = fields.Integer('Days relative to project')

    def action_save(self):
        for wizard in self:
            for service in wizard.service_ids:
                if not self.env.context.get('name_readonly'):
                    service.name = self.name
                if not self.env.context.get('internal_remarks_invisible'):
                    service.internal_remarks = self.internal_remarks
                if not self.env.context.get('days_relative_to_project_invisible'):
                    service.days_relative_to_project = self.days_relative_to_project
   
        action = { 'type': 'ir.actions.act_window_close' }
        return action

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        # Get the default service_ids from the action.context
        default_service_ids = self.env.context.get('default_service_ids')
        if not default_service_ids:
            raise UserError(_('No services selected'))
        
        services = self.env['riverflow.service'].browse(default_service_ids)
        defaultValues['service_ids'] = [(6, 0, services.ids)] # 6: replace the list of ids in the Many2many field
        
        if (len(services) == 1):
            service = services[0]
            defaultValues['name'] = service.name
            defaultValues['internal_remarks'] = service.internal_remarks
            defaultValues['days_relative_to_project'] = service['days_relative_to_project']
        
        return defaultValues