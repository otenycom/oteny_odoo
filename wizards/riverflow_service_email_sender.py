from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.fields import Command
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)


class RiverflowServiceEmailSenderWizard(models.TransientModel):
    _name = "riverflow.service.email.sender.wizard"
    _inherit = [
        "riverflow.service.wizard",
        "mail.render.mixin",
    ]
    _description = "Riverflow Service Email Sender Wizard"

    recipient_partner_ids = fields.Many2many(
        "res.partner",
        string="Recipients",
        help="The default recipients for the email can be set by adding followers to the chatter",
    )
    subject = fields.Char(string="Subject")
    body = fields.Html(
        string="Body",
        sanitize=False,
        render_engine="qweb",
        render_options={"post_process": True},
    )
    email_template_id = fields.Many2one(
        "mail.template",
        string="Email Template",
        domain="[('model_id', '=', 'riverflow.service')]",
        required=False,
    )

    # New fields for rendered content
    subject_rendered = fields.Char(
        string="Rendered Subject",
        compute="_compute_rendered_content",
        store=False,
    )
    body_rendered = fields.Html(
        string="Rendered Content",
        compute="_compute_rendered_content",
        store=False,
        sanitize=False,
    )

    # New editable fields that mirror the rendered content
    subject_updatable = fields.Char(
        string="Message Subject",
        compute="_compute_updatable_content",
        inverse="_inverse_subject_updatable",
        store=True,
    )
    body_updatable = fields.Html(
        string="Message Content",
        compute="_compute_updatable_content",
        inverse="_inverse_body_updatable",
        store=True,
        sanitize=False,
    )

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "riverflow_service_mail_attachments_rel",
        "wizard_id",
        "attachment_id",
        string="Attachments",
        compute="_compute_attachment_ids",
        readonly=False,
        store=True,
    )

    is_supply_order = fields.Boolean(
        "Is Supply Order",
        help="If checked, the service is a supply order, e.g a Taxi Order",
        required=False,
    )

    supplier_partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        help="The partner that is supplying the service",
        required=False,
    )

    supplier_email_formatted = fields.Char(
        "Supplier Email",
        compute="_compute_supplier_email_formatted",
        store=False,
    )

    supply_date = fields.Date(
        "Supply Date",
        help="The date the service is expected to be supplied",
        required=False,
    )

    supply_order_instructions = fields.Text(
        "Instructions for the supplier",
        help="Instructions for the supply order",
        required=False,
    )

    leg_ids = fields.One2many(
        "riverflow.service.email.sender.wizard.leg", "wizard_id", string="Supply Legs"
    )

    def get_visibility_defaults(self, transition_id):
        # normally the responsible team is hidden for end-states, but here it is visible
        # because we use it as the sender of the email
        default_values = super().get_visibility_defaults(transition_id)
        default_values["responsible_team_id_invisible"] = False
        return default_values

    @api.depends("subject_rendered", "body_rendered", "subject", "body")
    def _compute_updatable_content(self):
        for wizard in self:
            # Update if empty or if template fields changed
            if not wizard.subject_updatable or wizard.subject != wizard._origin.subject:
                wizard.subject_updatable = wizard.subject_rendered
            if not wizard.body_updatable or wizard.body != wizard._origin.body:
                wizard.body_updatable = wizard.body_rendered

    def _inverse_subject_updatable(self):
        # This method allows manual updates to subject_updatable to persist
        pass

    def _inverse_body_updatable(self):
        # This method allows manual updates to body_updatable to persist
        pass

    @api.depends("supplier_partner_id")
    def _compute_supplier_email_formatted(self):
        for wizard in self:
            wizard.supplier_email_formatted = wizard.supplier_partner_id.email_formatted

    @api.depends("email_template_id")
    def _compute_attachment_ids(self):
        for wizard in self:
            if wizard.email_template_id.attachment_ids:
                wizard.attachment_ids = wizard.email_template_id.attachment_ids
            else:
                wizard.attachment_ids = False

    def render(self):
        self._compute_rendered_content()
        self._compute_updatable_content()

    @api.depends("subject", "body", "records_to_transition_ids")
    def _compute_rendered_content(self):
        for wizard in self:
            if not wizard.records_to_transition_ids:
                wizard.subject_rendered = wizard.subject
                wizard.body_rendered = wizard.body
                # Update editable fields when template changes
                wizard.subject_updatable = wizard.subject
                wizard.body_updatable = wizard.body
                continue

            service = wizard.records_to_transition_ids[0]
            render_context = wizard._get_render_context(service, {})

            # Render subject
            wizard.subject_rendered = wizard._render_template(
                wizard.subject or self.email_template_id.subject,
                "riverflow.service",
                [service.id],
                engine="inline_template",
                add_context=render_context,
            )[service.id]

            # Render body
            # Add logging for service legs
            for leg in service.leg_ids:
                _logger.info(
                    f"Service {service.id} leg: sequence={leg.sequence}, "
                    f"from={leg.supply_from}, to={leg.supply_to}, "
                    f"supply_log_entry_id={leg.supply_log_entry_id.id if leg.supply_log_entry_id else None}"
                )

            wizard.body_rendered = wizard._render_template(
                wizard.body or self.email_template_id.body_html,
                "riverflow.service",
                [service.id],
                engine="qweb",
                add_context=render_context,
                options={"post_process": True},
            )[service.id]

            # Update editable fields when template changes
            wizard.subject_updatable = wizard.subject_rendered
            wizard.body_updatable = wizard.body_rendered

    def default_get_using_records(self, defaultValues, records_to_transition):
        super().default_get_using_records(defaultValues, records_to_transition)

        # Get default recipients from the first service record
        if records_to_transition:
            service = records_to_transition[0]
            default_recipients = service._get_default_recipients()
            if default_recipients:
                recipients = [
                    Command.link(partner_id) for partner_id in default_recipients.ids
                ]
                if "recipient_partner_ids" in defaultValues:
                    defaultValues["recipient_partner_ids"].extend(recipients)
                else:
                    defaultValues["recipient_partner_ids"] = recipients

            # Initialize leg_ids from service's existing legs
            if service.leg_ids:
                leg_commands = []
                for leg in service.leg_ids:
                    leg_commands.append(
                        Command.create(
                            {
                                "sequence": leg.sequence,
                                "supply_from": leg.supply_from,
                                "supply_to": leg.supply_to,
                                "supply_instructions": leg.supply_instructions,
                                "supply_log_entry_id": leg.supply_log_entry_id.id,
                            }
                        )
                    )
                defaultValues["leg_ids"] = leg_commands

    @api.onchange("email_template_id")
    def onchange_email_template_id(self):
        if self.email_template_id:
            self.subject = self.email_template_id.subject
            self.body = self.email_template_id.body_html
            self.render()

    @api.onchange(
        "leg_ids",
        "supply_date",
        "responsible_team_id",
        "supplier_partner_id",
        "is_supply_order",
    )
    def onchange_supply_fields(self):
        self.render()

    def _get_render_context(self, service, vals):
        res_id = vals.get("res_id") or service.res_id
        if res_id:
            """TODO: move this to rivermen module"""
            log_entry_id = self.env["rivermen.log.entry"].browse(res_id)
        else:
            log_entry_id = None

        if self.is_supply_order:
            write_vals = {}
            self.update_write_values(service, write_vals)
            service.write(write_vals)

        if self.is_supply_order:
            return {
                "service": service,
                "log_entry": log_entry_id,
                "company": service.company_id,
            }
        else:
            return {
                "service": service,
                "log_entry": log_entry_id,
                "company": service.company_id,
            }

    def update_write_values(self, service, vals):
        super(RiverflowServiceEmailSenderWizard, self).update_write_values(
            service, vals
        )
        # new services are automatically assigned a name equal to the email subject
        isNewService = isinstance(service.id, models.NewId)
        if isNewService and not vals.get("name"):
            subject = self.subject_updatable
            vals["name"] = subject

        if self.is_supply_order:
            # Write supplier reference to service
            vals["supplier_partner_id"] = self.supplier_partner_id.id
            vals["supply_date"] = self.supply_date
            vals["supply_order_instructions"] = self.supply_order_instructions

            # Sync legs with service - first remove existing legs then add new ones
            leg_commands = [Command.clear()]
            for leg in self.leg_ids:
                leg_vals = {
                    "sequence": leg.sequence,
                    "supply_from": leg.supply_from,
                    "supply_to": leg.supply_to,
                    "supply_instructions": leg.supply_instructions,
                    "supply_log_entry_id": leg.supply_log_entry_id.id,
                }
                leg_commands.append(Command.create(leg_vals))

            vals["leg_ids"] = leg_commands

            # Set initial deadline
            vals["use_project_deadline_from"] = "self"
            vals["project_deadline"] = fields.Date.context_today(self)

    def create_related_records(self, service):
        super(RiverflowServiceEmailSenderWizard, self).create_related_records(service)
        self._send_email(service)

    def _send_email(self, service):
        recipient_ids = self.recipient_partner_ids

        if self.is_supply_order:
            recipient_ids = recipient_ids.union(self.supplier_partner_id)

        if not recipient_ids:
            raise UserError(_("Please select at least one recipient."))

        # Use updatable content for sending
        safe_body = tools.html_sanitize(self.body_updatable)

        allowed_domains = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("riverflow.restrict_email_recipients_to", "")
            .split(",")
        )
        allowed_domains = [
            domain.strip().lower() for domain in allowed_domains if domain.strip()
        ]

        if allowed_domains:
            invalid_recipients = recipient_ids.filtered(
                lambda partner: partner.email
                and not any(
                    partner.email.lower().endswith(f"@{domain}")
                    for domain in allowed_domains
                )
            )

            if invalid_recipients:
                raise ValueError(
                    _(
                        "Email sending is restricted to specific domains (%s). "
                        "The following recipients have invalid email domains: %s"
                    )
                    % (
                        ", ".join(allowed_domains),
                        ", ".join(invalid_recipients.mapped("email_formatted")),
                    )
                )

        if not self.subject_updatable:
            raise ValueError(_("Subject is required"))

        if not self.body_updatable:
            raise ValueError(_("Body is required"))

        # Post the message, add followers to the chatter, and don't subscribe them to the chatter
        service.with_context(
            mail_post_autofollow=True, mail_create_nosubscribe=True
        ).message_post(
            message_type="email",
            subject=self.subject_updatable,
            partner_ids=recipient_ids.ids,
            body=safe_body,
            subtype_id=self.env.ref("mail.mt_comment").id,
            email_add_signature=False,
            email_layout_xmlid=self.email_template_id.email_layout_xmlid,
            attachment_ids=self.attachment_ids.ids,
        )


class RiverflowServiceEmailSenderWizardLeg(models.TransientModel):
    _name = "riverflow.service.email.sender.wizard.leg"
    _description = "Supply Order Leg in Email Wizard"
    _order = "sequence,id"

    wizard_id = fields.Many2one(
        "riverflow.service.email.sender.wizard", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    supply_from = fields.Char("From")
    supply_to = fields.Char("To")
    supply_instructions = fields.Text(
        "Instructions",
        help="Instructions to the supplier about this leg of the supply order",
    )
