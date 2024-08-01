from odoo import models, fields
from odoo.addons.riverflow.wizards.riverflow_transition_wizard import (
    TransitionWizard,
)


class ServiceWizard(models.TransientModel):
    _name = "riverflow.service.wizard"
    _inherit = "riverflow.transition.wizard"
    _description = "Service Wizard"

    _workflow_model = "riverflow.service"
    record_ids = fields.Many2many("riverflow.service")

    # from service record
    name = fields.Char("Service Name")
    days_relative_to_project = fields.Integer("Days relative to project")

    # new chatter remark (todo: move to the base class)
    new_remark = fields.Html("New Remark")

    def set_property_values(self, service):
        if not self.env.context.get("name_readonly"):
            service.name = self.name

        if not self.env.context.get("days_relative_to_project_invisible"):
            service.days_relative_to_project = self.days_relative_to_project

    def create_related_records(self, service):
        if not self.env.context.get("new_remark_invisible") and self.new_remark:
            self.env["mail.message"].create(
                {
                    "body": self.new_remark,
                    "model": "riverflow.service",
                    "res_id": service.id,
                    "message_type": "comment",
                    "subtype_id": self.env.ref("mail.mt_note").id,
                }
            )
