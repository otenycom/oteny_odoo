from odoo import api, fields, models, Command
from odoo.exceptions import UserError


class RiverflowEnterAirlineTicketWizard(models.TransientModel):
    _name = "riverflow.enter.airline.ticket.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Enter Airline Ticket Wizard"

    date = fields.Date(string="Date", required=True)
    supply_unit_price = fields.Float(string="Cost", required=True)
    notes = fields.Text(string="Notes")  # Flight details will be entered here
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "riverflow_airline_ticket_wizard_attachments_rel",  # Renamed relation table
        "wizard_id",
        "attachment_id",
        string="Attachments",
    )

    use_existing_attachment = fields.Boolean(
        string="Use Existing Attachment",
        default=False,
    )

    @api.model
    def default_get_using_records(self, defaultValues, records_to_transition):
        super().default_get_using_records(defaultValues, records_to_transition)

        if len(records_to_transition) != 1:
            return

        service = records_to_transition[0]

        if service.most_recent_attachment_id:
            defaultValues["use_existing_attachment"] = True

        defaultValues["date"] = service.deadline
        if service.supply_unit_price:
            defaultValues["supply_unit_price"] = service.supply_unit_price

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)

        if self.date:
            vals["use_project_deadline_from"] = "self"
            vals["project_deadline"] = self.date

        vals["supply_unit_price"] = self.supply_unit_price

        if self.use_existing_attachment:
            # If using existing, don't process new attachments and don't raise error if none are attached
            pass
        elif self.attachment_ids:
            if len(self.attachment_ids) > 1:
                raise UserError("Please attach only one file.")
            # Post the single new attachment
            service.message_post(
                attachment_ids=self.attachment_ids.ids,
            )
        elif service.message_attachment_count == 0:
            raise UserError("Please attach the ticket file.")
