from odoo import api, fields, models, Command
from odoo.exceptions import UserError


class RiverflowEnterTrainTicketWizard(models.TransientModel):
    _name = "riverflow.enter.train.ticket.wizard"
    _inherit = ["riverflow.service.wizard"]
    _description = "Enter Train Ticket Wizard"

    date = fields.Date(string="Date", required=True)
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
        if len(service.leg_ids) > 0:

            defaultValues["from_station"] = service.leg_ids[0].supply_from
            defaultValues["to_station"] = service.leg_ids[0].supply_to
            defaultValues["notes"] = service.leg_ids[0].supply_instructions

            if len(service.leg_ids) == 2:
                defaultValues["is_round_trip"] = True

            defaultValues["price"] = sum(leg.supply_cost_amount for leg in service.leg_ids)

    def update_write_values(self, service, vals):
        super().update_write_values(service, vals)

        if self.date:
            vals["project_deadline"] = self.date

        if self.use_existing_attachment:
            # Using existing attachment from the service
            pass
        elif self.attachment_ids:
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
            # No attachments at all - require at least one
            raise UserError("Please attach at least one file.")

        self._process_legs(service)

    def _process_legs(self, service):
        """Create or update legs on the service from wizard field values.

        Hook method: downstream modules (e.g. crewradar_wilma) can override
        to skip manual leg creation when AI parsing already produced legs
        with richer data (place_ids, distance, duration).
        """
        service.write(
            {
                "leg_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "supply_from": self.from_station,
                            "supply_to": self.to_station,
                            "supply_cost_amount": (self.price if not self.is_round_trip else self.price / 2),
                            "supply_instructions": self.notes,
                            "pax_ids": [
                                Command.clear(),
                                Command.create(
                                    {
                                        "log_entry_id": service.log_entry_id.id,
                                    }
                                ),
                            ],
                        }
                    ),
                ]
                + (
                    [
                        Command.create(
                            {
                                "supply_from": self.to_station,
                                "supply_to": self.from_station,
                                "supply_cost_amount": self.price / 2,
                                "supply_instructions": self.notes,
                                "pax_ids": [
                                    Command.clear(),
                                    Command.create(
                                        {
                                            "log_entry_id": service.log_entry_id.id,
                                        }
                                    ),
                                ],
                            }
                        )
                    ]
                    if self.is_round_trip
                    else []
                ),
            }
        )

    def _after_ticket_attachment_posted(self, service):
        """Hook called after new ticket attachments are posted to the service.
        Override in downstream modules to add post-upload processing (e.g. PDF parsing)."""
        pass
