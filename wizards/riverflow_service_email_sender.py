from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.addons.riverflow.wizards.riverflow_transition_wizard import (
    TransitionWizard,
)
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


class RiverflowServiceEmailSenderWizard(models.TransientModel):
    _name = "riverflow.service.email.sender.wizard"
    _inherit = "riverflow.transition.wizard"
    _description = "Riverflow Service Email Sender Wizard"

    _workflow_model = "riverflow.service"
    record_ids = fields.Many2many("riverflow.service")

    partner_ids = fields.Many2many("res.partner", string="Recipients")
    subject = fields.Char(string="Subject")
    body = fields.Html(string="Message Body")
    template_id = fields.Many2one("mail.template", string="Email Template")

    @api.model
    def default_get(self, fields):
        res = super(RiverflowServiceEmailSenderWizard, self).default_get(fields)
        context = self.env.context
        if context.get("active_model") == "riverflow.service" and context.get(
            "active_id"
        ):
            service = self.env["riverflow.service"].browse(context["active_id"])
            # todo: store the template in the service
        #     if service.email_template_id:
        #         res["template_id"] = service.email_template_id.id
        #         template = service.email_template_id
        #         res["subject"] = template.subject
        #         res["body"] = template.body_html
        return res

    @api.onchange("template_id")
    def onchange_template_id(self):
        if self.template_id:
            self.subject = self.template_id.subject
            self.body = self.template_id.body_html

    def action_send_email(self, service):
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(_("Please select at least one recipient."))

        # Create the context dictionary once
        render_context = {
            "service": service,
            "log_entry": service.log_entry_id,
            "company": self.env.company,
        }

        # Render the email template
        rendered_body = self.env["mail.render.mixin"]._render_template(
            self.template_id.body_html,
            service._name,
            [service.id],
            engine="qweb",
            add_context=render_context,
            options={
                "preserve_comments": True,
                "post_process": True,
            },
        )[service.id]

        rendered_subject = self.env["mail.render.mixin"]._render_template(
            self.template_id.subject,
            service._name,
            [service.id],
            engine="inline_template",
            add_context=render_context,
        )[service.id]

        # Sanitize the rendered body
        safe_body = tools.html_sanitize(rendered_body)

        # Post the message in the chatter and send notifications
        service.message_post(
            body=safe_body,
            subject=rendered_subject,
            partner_ids=self.partner_ids.ids,
            message_type="email",
            subtype_id=self.env.ref("mail.mt_comment").id,
        )

        # Log the email content for debugging
        partner_info = ", ".join(
            [f"{partner.name} ({partner.email})" for partner in self.partner_ids]
        )
        _logger.info(f"Email sent and logged in chatter. Subject: {rendered_subject}")
        _logger.info(f"Recipients: {partner_info}")
        _logger.info(f"Email body: {safe_body}")

        return True

    def updated_property_values(self, service, vals):
        # Add any specific property updates here if needed
        pass

    def create_related_records(self, service):
        super(RiverflowServiceEmailSenderWizard, self).create_related_records(service)
        self.action_send_email(service)
