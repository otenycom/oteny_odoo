from odoo import api, fields, models


class SetDeadlineTomorrowWizard(models.TransientModel):
    _name = "riverflow.set.deadline.tomorrow.wizard"
    _inherit = "riverflow.service.wizard"
    _description = "Set Deadline Tomorrow Wizard"

    # Override tag_ids with explicit relation name to avoid table name length issue
    tag_ids = fields.Many2many(
        "riverflow.service.tag",
        "riverflow_set_deadline_tag_rel",
        "wizard_id",
        "tag_id",
        string="Tags",
    )

    supply_actual_date = fields.Date(
        string="Actual Trip Date",
        help="The date when the trip actually occurred. This will be saved for billing purposes.",
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        """Set deadline to tomorrow and capture actual trip date"""
        super().default_get_using_records(defaultValues, records_to_transition)

        if len(records_to_transition) == 1:
            service = records_to_transition[0]
            # Set supply_actual_date to the current service deadline (the original trip date)
            defaultValues["supply_actual_date"] = service.supply_date

        # Set deadline to tomorrow for administrative task urgency
        defaultValues["project_deadline"] = fields.Date.add(fields.Date.today(), days=1)
        defaultValues["use_project_deadline_from"] = "self"

    def update_write_values(self, service, vals):
        """Capture actual trip date and set deadline to tomorrow"""
        super().update_write_values(service, vals)

        # Save the actual supply date for billing purposes
        vals["supply_actual_date"] = self.supply_actual_date

        # Force the deadline to tomorrow and switch to 'self' mode
        vals["project_deadline"] = self.project_deadline
        vals["use_project_deadline_from"] = "self"
        vals["days_relative_to_project"] = 0
