from odoo import api, fields, models


class RiverflowEnterTrainTicketWizard(models.TransientModel):
    _name = "riverflow.enter.train.ticket.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Enter Train Ticket Wizard"

    date = fields.Date(string="Date")
    from_station = fields.Char(string="From")
    to_station = fields.Char(string="To")
    is_round_trip = fields.Boolean(string="Is Round Trip")
    price = fields.Float(string="Price")
    notes = fields.Text(string="Notes")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "riverflow_train_ticket_wizard_attachments_rel",
        "wizard_id",
        "attachment_id",
        string="Attachments",
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        super().default_get_using_records(defaultValues, records_to_transition)

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)
