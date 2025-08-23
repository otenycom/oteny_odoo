# audit_log/models/audit_log.py
from odoo import fields, models


class OtenyAuditLog(models.Model):
    _name = "oteny.audit.log"
    _description = "Oteny Audit Log"
    _order = "id desc"

    model_name = fields.Char(required=True)
    record_id = fields.Integer(required=True)
    record_display_name = fields.Char(string="Record Name")
    field_name = fields.Char(required=True)
    old_value = fields.Text()
    new_value = fields.Text()
    old_value_display_name = fields.Char(string="Old Value Name")
    new_value_display_name = fields.Char(string="New Value Name")
    change_type = fields.Selection(
        [("insert", "Insert"), ("update", "Update"), ("delete", "Delete")], required=True
    )
