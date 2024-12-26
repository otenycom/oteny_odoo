from odoo import api, fields, models


class RiverflowSupplierConfirmedWizard(models.TransientModel):
    _name = "riverflow.supplier.confirmed.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Supplier Confirmed Wizard"

    supply_date = fields.Date(
        string="Supply Date",
        help="The confirmed date when the service will be supplied",
    )

    project_deadline = fields.Date(
        string="Registration Deadline",
        help="The deadline for hand over to back office for billing purposes, defaults to supply date but you may want to set it to a later date",
    )
    unreviewed_message_count = fields.Integer(
        string="Unreviewed Messages",
        help="Unreviewed messages from the supplier, see the service chatter",
    )
    mark_external_messages_as_reviewed = fields.Boolean(
        string="Mark as Reviewed",
        help="Mark all external messages as reviewed",
        default=True,
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        super().default_get_using_records(defaultValues, records_to_transition)

        if records_to_transition:
            service = records_to_transition[0]
            defaultValues["project_deadline"] = service.supply_date

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)
        vals.update(
            {
                "project_deadline": self.project_deadline,
                "use_project_deadline_from": "self",  # Ensure we use the manually set deadline
                "supply_date": self.supply_date,
            }
        )
        if self.mark_external_messages_as_reviewed and self.unreviewed_message_count:
            vals["last_external_message_review_time"] = fields.Datetime.now()
