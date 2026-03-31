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

    supply_time_of_day = fields.Float(
        string="Trip Time",
        help="Time of day when the trip occurred (e.g. pickup time, departure time).",
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        """Set deadline based on supply date and capture actual trip date.

        If supply_date is in the future, deadline is set to supply_date + 1 day.
        Otherwise deadline is set to tomorrow for administrative task urgency.
        """
        super().default_get_using_records(defaultValues, records_to_transition)

        today = fields.Date.today()
        tomorrow = fields.Date.add(today, days=1)

        if len(records_to_transition) == 1:
            service = records_to_transition[0]
            # Set supply_actual_date to the current service deadline (the original trip date)
            defaultValues["supply_actual_date"] = service.supply_date
            if service.supply_time_of_day:
                defaultValues["supply_time_of_day"] = service.supply_time_of_day

            # If supply_date is in the future, deadline = supply_date + 1 day
            if service.supply_date and service.supply_date > today:
                defaultValues["project_deadline"] = fields.Date.add(service.supply_date, days=1)
            else:
                defaultValues["project_deadline"] = tomorrow
        else:
            defaultValues["project_deadline"] = tomorrow

        defaultValues["use_project_deadline_from"] = "self"

    def update_write_values(self, service, vals):
        """Capture actual trip date/time and use the deadline as entered by the user."""
        super().update_write_values(service, vals)

        vals["supply_actual_date"] = self.supply_actual_date
        if self.supply_time_of_day:
            vals["supply_time_of_day"] = self.supply_time_of_day
        vals["project_deadline"] = self.project_deadline
        vals["use_project_deadline_from"] = "self"
        vals["days_relative_to_project"] = 0
