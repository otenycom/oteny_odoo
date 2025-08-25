from odoo import fields, models


class OtenyAuditLogAggregated(models.Model):
    _name = "oteny.audit.log.aggregated"
    _description = "Aggregated Audit Log (including children)"
    _auto = False
    _order = "id desc"

    # --- Fields from oteny.audit.log ---
    transaction_id = fields.Integer(readonly=True, string="Transaction ID")
    model_name = fields.Char(readonly=True)
    record_id = fields.Integer(readonly=True, string="Record ID")
    record_ref = fields.Reference(
        string="Record Link",
        selection="_selection_record_ref",
        compute="_compute_record_ref",
        readonly=True,
    )
    record_display_name = fields.Char(string="Record Name", readonly=True)
    field_name = fields.Char(readonly=True, string="Field Raw Name")
    field_display_name = fields.Char(string="Field", readonly=True)
    old_value = fields.Text(string="Old Value Raw", readonly=True)
    new_value = fields.Text(string="New Value Raw", readonly=True)
    old_value_display_name = fields.Char(string="Old Value", readonly=True)
    new_value_display_name = fields.Char(string="New Value", readonly=True)
    change_type = fields.Selection(
        [("insert", "Insert"), ("update", "Update"), ("delete", "Delete")],
        readonly=True,
    )
    create_date = fields.Datetime(string="Timestamp", readonly=True)
    create_uid = fields.Many2one("res.users", string="User", readonly=True)

    # --- Fields to distinguish parent/child logs ---
    is_child_log = fields.Boolean(string="Is Child Log?", readonly=True)
    child_model_name = fields.Char(string="Child Model", readonly=True)
    child_record_id = fields.Integer(string="Child Record ID", readonly=True)
    child_record_ref = fields.Reference(
        string="Child Record Link",
        selection="_selection_record_ref",
        compute="_compute_child_record_ref",
        readonly=True,
    )

    def _selection_record_ref(self):
        return self.env["oteny.audit.log"]._selection_record_ref()

    def _compute_record_ref(self):
        for log in self:
            log.record_ref = (
                f"{log.model_name},{log.record_id}" if log.model_name and log.record_id else False
            )

    def _compute_child_record_ref(self):
        for log in self:
            if log.is_child_log and log.child_model_name and log.child_record_id:
                log.child_record_ref = f"{log.child_model_name},{log.child_record_id}"
            else:
                log.child_record_ref = False

    @property
    def _table_query(self):
        return """
            (
                -- Direct logs for a parent record
                SELECT
                    id,
                    create_date,
                    create_uid,
                    transaction_id,
                    model_name,
                    record_id,
                    record_display_name,
                    field_name,
                    field_display_name,
                    old_value,
                    new_value,
                    old_value_display_name,
                    new_value_display_name,
                    change_type,
                    FALSE AS is_child_log,
                    NULL AS child_model_name,
                    NULL AS child_record_id
                FROM
                    oteny_audit_log
            )
            UNION ALL
            (
                -- Child logs linked to a parent record
                SELECT
                    (ref.audit_log_id + 1000000000) AS id,
                    log.create_date,
                    log.create_uid,
                    log.transaction_id,
                    ref.parent_model_name AS model_name,
                    ref.parent_record_id AS record_id,
                    log.record_display_name,
                    log.field_name,
                    log.field_display_name,
                    log.old_value,
                    log.new_value,
                    log.old_value_display_name,
                    log.new_value_display_name,
                    log.change_type,
                    TRUE AS is_child_log,
                    log.model_name AS child_model_name,
                    log.record_id AS child_record_id
                FROM
                    oteny_audit_log_parent_ref ref
                JOIN
                    oteny_audit_log log ON ref.audit_log_id = log.id
            )
        """
