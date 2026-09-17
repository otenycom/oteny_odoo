from odoo import api, fields, models


class RiverflowSupplierConfirmedWizard(models.TransientModel):
    _name = "riverflow.supplier.confirmed.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Supplier Confirmed Wizard"

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

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)

        if self.mark_external_messages_as_reviewed and self.unreviewed_message_count:
            vals["last_external_message_review_time"] = fields.Datetime.now()
