from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
import logging
from odoo.fields import Command

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

    @api.onchange("email_template_id")
    def onchange_email_template_id(self):
        if self.email_template_id:
            self.subject = self.email_template_id.subject
            self.body = self.email_template_id.body_html

    def _get_render_context(self, service, vals):
        res_id = vals.get("res_id") or service.res_id
        if res_id:
            """TODO: move this to rivermen module"""
            log_entry_id = self.env["rivermen.log.entry"].browse(res_id)
        else:
            log_entry_id = None
        return {
            "service": service,
            "log_entry": log_entry_id,
            "company": service.company_id,
        }

    def _get_rendered_subject(self, service, vals):
        render_context = self._get_render_context(service, vals)
        subject_rendered = self._render_template(
            self.subject or "",
            "riverflow.service",
            [service.id],
            engine="inline_template",
            add_context=render_context,
        )[service.id]
        return subject_rendered

    def _generate_default_name(self, subject):
        max_length = 100
        truncated_subject = subject[:max_length].strip()
        if len(subject) > max_length:
            truncated_subject += "..."
        return f"{truncated_subject}"

    def update_write_values(self, service, vals):
        super(RiverflowServiceEmailSenderWizard, self).update_write_values(
            service, vals
        )
        # new services are automatically assigned a name equal to the email subject
        isNewService = isinstance(service.id, models.NewId)
        if isNewService and not vals.get("name"):
            subject_rendered = self._get_rendered_subject(service, vals)
            default_name = self._generate_default_name(subject_rendered)
            vals["name"] = default_name

    def create_related_records(self, service):
        super(RiverflowServiceEmailSenderWizard, self).create_related_records(service)
        self._send_email(service)

    def _send_email(self, service):
        if not self.recipient_partner_ids:
            raise UserError(_("Please select at least one recipient."))

        vals = {}  # uncommitted new property values
        render_context = self._get_render_context(service, vals)
        subject_rendered = self._get_rendered_subject(service, vals)

        body_rendered = self._render_template(
            self.body,
            "riverflow.service",
            [service.id],
            engine="qweb",
            add_context=render_context,
            options={"post_process": True},
        )[service.id]

        # Sanitize the rendered body
        safe_body = tools.html_sanitize(body_rendered)

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
            invalid_recipients = self.recipient_partner_ids.filtered(
                lambda partner: partner.email
                and not any(
                    partner.email.lower().endswith(f"@{domain}")
                    for domain in allowed_domains
                )
            )

            if invalid_recipients:
                raise UserError(
                    _(
                        "Email sending is restricted to specific domains (%s). "
                        "The following recipients have invalid email domains: %s"
                    )
                    % (
                        ", ".join(allowed_domains),
                        ", ".join(invalid_recipients.mapped("name")),
                    )
                )

        # Post the message
        service.with_context(
            mail_post_autofollow=False, mail_create_nosubscribe=True
        ).message_post(
            message_type="email",
            subject=subject_rendered,
            partner_ids=self.recipient_partner_ids.ids,
            body=safe_body,
            subtype_id=self.env.ref("mail.mt_comment").id,
            email_add_signature=False,
            email_layout_xmlid=self.email_template_id.email_layout_xmlid,
        )
