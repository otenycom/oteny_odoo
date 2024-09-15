from odoo import models, fields, api


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
        string="Deadline From",
        required=False,
    )
    use_project_deadline_from_invisible = fields.Boolean(
        compute="_compute_field_visibility"
    )
    project_deadline = fields.Date(
        "Project deadline",
        help="The services are timed relative to this deadline",
    )
    project_deadline_invisible = fields.Boolean(compute="_compute_field_visibility")

    days_relative_to_project = fields.Integer("Relative Deadline (days)")
    days_relative_to_project_invisible = fields.Boolean(
        compute="_compute_field_visibility"
    )

    # the container of the service (log_entry, employee, etc)
    res_id = fields.Integer(string="Subject of Service ID", required=False)
    res_model = fields.Char(
        string="Subject of Service Model Name",
    )

    def updated_property_values(self, service, vals):
        super().updated_property_values(service, vals)
        vals["res_id"] = self.res_id
        vals["res_model"] = self.res_model

        if not self.env.context.get("name_readonly"):
            vals["name"] = self.name

        if not self.days_relative_to_project_invisible:
            vals["days_relative_to_project"] = self.days_relative_to_project

        if not self.use_project_deadline_from_invisible:
            vals["use_project_deadline_from"] = self.use_project_deadline_from

    @api.depends("transition_id")
    def _compute_field_visibility(self):
        super()._compute_field_visibility()
        for wizard in self:
            wizard.project_deadline_invisible = self._is_to_end_state()
            wizard.use_project_deadline_from_invisible = self._is_to_end_state()
            wizard.days_relative_to_project_invisible = self._is_to_end_state()
