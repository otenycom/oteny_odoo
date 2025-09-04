from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class OtenyAuditMixin(models.AbstractModel):
    """
    Mixin to add audit log functionality to models.
    Provides audit_log_ids field that shows audit logs for the current record.
    """

    _name = "oteny.audit.mixin"
    _description = "Oteny Audit Mixin"

    audit_log_ids = fields.One2many(
        "oteny.audit.log.aggregated",
        string="Audit Logs",
        compute="_compute_audit_log_ids",
        help="Audit logs for this record showing all changes made to it and its related records",
    )

    @api.depends()
    def _compute_audit_log_ids(self):
        """
        Compute audit logs for the current record.
        This includes both direct audit logs and child audit logs related to this record.
        """
        for record in self:
            if not record.id:
                record.audit_log_ids = False
                continue

            # Get audit logs for this record (direct logs)
            direct_logs = self.env["oteny.audit.log.aggregated"].search(
                [
                    ("model_name", "=", record._name),
                    ("record_id", "=", record.id),
                ]
            )

            record.audit_log_ids = direct_logs
