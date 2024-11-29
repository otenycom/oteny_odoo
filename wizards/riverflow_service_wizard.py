from odoo import models, fields, api


class ServiceWizard(models.TransientModel):
    _name = "riverflow.service.wizard"  #
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
        string="Deadline From",
        required=False,
    )
    use_project_deadline_from_invisible = fields.Boolean()
    project_deadline = fields.Date(
        "Project deadline",
        help="The services are timed relative to this deadline",
    )
    project_deadline_invisible = fields.Boolean()

    days_relative_to_project = fields.Integer("Relative Deadline (days)")
    days_relative_to_project_invisible = fields.Boolean()

    # the container of the service (log_entry, employee, etc)
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)
        vals["res_id"] = self.res_id
        vals["res_model"] = self.res_model

        if not self.env.context.get("name_readonly"):
            vals["name"] = self.name

        if not self.days_relative_to_project_invisible:
            vals["days_relative_to_project"] = self.days_relative_to_project

        if not self.use_project_deadline_from_invisible:
            vals["use_project_deadline_from"] = self.use_project_deadline_from
            if self.use_project_deadline_from == "self":
                vals["project_deadline"] = self.project_deadline
                vals["days_relative_to_project"] = 0

    def get_visibility_defaults(self, transition_id):
        visibility_defaults = super().get_visibility_defaults(transition_id)
        is_end_state = transition_id.to_state_id.is_end_state
        visibility_defaults["project_deadline_invisible"] = is_end_state
        visibility_defaults["use_project_deadline_from_invisible"] = is_end_state
        visibility_defaults["days_relative_to_project_invisible"] = is_end_state

        return visibility_defaults
