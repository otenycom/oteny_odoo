from odoo import models, fields
from odoo.addons.riverflow.wizards.riverflow_transition_wizard import (
    TransitionWizard,
)


class ServiceWizard(models.TransientModel):
    _name = "riverflow.service.wizard"
    _inherit = "riverflow.transition.wizard"
    _description = "Service Wizard"

    _workflow_model = "riverflow.service"
    records_to_transition_ids = fields.Many2many("riverflow.service")

    # from service record
    name = fields.Char("Service Name")
    use_project_deadline_from = fields.Selection(
        [
            ("self", "Self"),
            ("root", "Root Service"),
        ],
        string="Project Deadline From",
        required=False,
    )
    project_deadline = fields.Date(
        "Project deadline",
        help="The services are timed relative to this deadline",
    )
    days_relative_to_project = fields.Integer("Days relative to project-deadline")
    # the container of the service (log_entry, employee, etc)
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )

    # new chatter remark (todo: move to the base class)
    new_remark = fields.Html("New Remark")

    def updated_property_values(self, service, vals):
        if not self.env.context.get("name_readonly"):
            vals["name"] = self.name

        if not self.env.context.get("days_relative_to_project_invisible"):
            vals["days_relative_to_project"] = self.days_relative_to_project

        vals["use_project_deadline_from"] = self.use_project_deadline_from
        vals["res_id"] = self.res_id
        vals["res_model"] = self.res_model

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
