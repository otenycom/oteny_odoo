# oteny_audit/models/oteny_audit_log_parent_ref.py
from odoo import fields, models


class OtenyAuditLogParentRef(models.Model):
    _name = "oteny.audit.log.parent.ref"
    _description = "Oteny Audit Log Parent Reference"

    audit_log_id = fields.Many2one(
        "oteny.audit.log",
        required=True,
        ondelete="cascade",
        index=True,
        string="Audit Log Entry",
    )
    parent_model_name = fields.Char(required=True, index=True, string="Parent Model")
    parent_record_id = fields.Integer(required=True, index=True, string="Parent Record ID")
    parent_record_display_name = fields.Char(string="Parent Record Name")

    # Removed unique constraint to allow multiple parent references per audit log
    # This enables hierarchical parent reference tracking (immediate parent, grandparent, etc.)
