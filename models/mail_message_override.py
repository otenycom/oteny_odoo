from odoo import models


class MailMessage(models.Model):
    """Audit-log integration for chatter messages.

    Intent: chatter messages on a business record are cascade-deleted when the
    record is unlinked, so the audit log is the only place that can preserve
    them after that point. We keep audit on `mail.message` and HTML-strip the
    `body` field (≈94% size reduction observed in production) so storage stays
    bounded while the prose remains readable for forensic purposes.
    """

    _inherit = "mail.message"

    # Strip HTML to plain text in the audit log copy of `body` (raw + display).
    # `mail.message` is itself in `OtenyAuditLog._model_parent_keys` mapped to
    # the polymorphic `model,res_id` parent reference, so audit log rows
    # automatically link to the business record's audit trail.
    _oteny_audit_html_strip_fields = {"body"}
