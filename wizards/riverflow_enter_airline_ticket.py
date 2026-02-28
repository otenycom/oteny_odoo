from odoo import api, fields, models, Command
from odoo.exceptions import UserError


class RiverflowEnterAirlineTicketWizard(models.TransientModel):
    _name = "riverflow.enter.airline.ticket.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Enter Airline Ticket Wizard"

    date = fields.Date(string="Date", required=True)
    supply_unit_price = fields.Float(string="Cost", required=True)
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

        defaultValues["date"] = fields.Date.today()
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
            # https://3.basecamp.com/5527227/buckets/38887735/todos/9117347114 - Flight need multiple attachments
            # Post new files to the service chatter. Include file names as body
            # text so Odoo's JS showDelete logic sees hasTextContent=true and
            # renders the delete button (without body text, single-attachment
            # notification messages have no way to be removed from the chatter).
            att_names = ", ".join(self.attachment_ids.mapped("name"))
            service.message_post(
                body=att_names,
                attachment_ids=self.attachment_ids.ids,
            )
            # Re-link attachments from the transient wizard to the service record.
            # Odoo's _process_attachments_for_post only re-links attachments from
            # mail.compose.message; wizard-originated attachments stay orphaned
            # on res_model='wizard' / res_id=0 which breaks server-side delete
            # access checks. Follows the pattern from purchase_order.py.
            self.attachment_ids.write(
                {"res_model": service._name, "res_id": service.id}
            )
            self._after_ticket_attachment_posted(service)
        elif service.message_attachment_count == 0:
            raise UserError("Please attach the ticket file.")

    def _after_ticket_attachment_posted(self, service):
        """Hook called after new ticket attachments are posted to the service.
        Override in downstream modules to add post-upload processing (e.g. PDF parsing)."""
        pass
