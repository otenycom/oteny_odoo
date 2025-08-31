# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class OtenyAuditLogAggregatedDisplay(models.Model):
    _name = "oteny.audit.log.aggregated.display"
    _description = "Audit Log Aggregated Display"
    _auto = False
    _order = "transaction_id DESC, display_sequence ASC, create_date DESC, id DESC"

    id = fields.Integer(string="ID", readonly=True)
    audit_log_id = fields.Integer(string="Audit Log ID", readonly=True)
    create_date = fields.Datetime(string="Created Date", readonly=True)
    create_uid = fields.Many2one("res.users", string="Created By", readonly=True)
    transaction_id = fields.Integer(string="Transaction ID", readonly=True)
    model_name = fields.Char(string="Model Name", readonly=True)
    model_display_name = fields.Char(string="Model Display Name", readonly=True)
    record_id = fields.Integer(string="Record ID", readonly=True)
    record_display_name = fields.Char(string="Record Display Name", readonly=True)
    parent_record_display_name = fields.Char(string="Parent Record Display Name", readonly=True)
    field_name = fields.Char(string="Field Name", readonly=True)
    field_display_name = fields.Char(string="Field Display Name", readonly=True)
    field_model_name = fields.Char(string="Field Model Name", readonly=True)
    field_model_display_name = fields.Char(string="Field Model Display Name", readonly=True)
    old_value = fields.Text(string="Old Value", readonly=True)
    new_value = fields.Text(string="New Value", readonly=True)
    old_value_display_name = fields.Text(string="Old Value Display Name", readonly=True)
    new_value_display_name = fields.Text(string="New Value Display Name", readonly=True)
    change_type = fields.Char(string="Change Type", readonly=True)
    is_child_log = fields.Boolean(string="Is Child Log", readonly=True)
    child_model_name = fields.Char(string="Child Model Name", readonly=True)
    child_model_display_name = fields.Char(string="Child Model Display Name", readonly=True)
    child_record_id = fields.Integer(string="Child Record ID", readonly=True)
    highlight_row_type = fields.Char(string="Highlight Row Type", compute="_compute_highlight")
    highlight_row = fields.Boolean(string="Highlight Row", compute="_compute_highlight")
    row_type = fields.Char(string="Row Type", readonly=True)
    caption = fields.Text(string="Caption", readonly=True)
    display_sequence = fields.Integer(string="Display Sequence", readonly=True)

    @api.depends("row_type")
    def _compute_highlight(self):
        for record in self:
            if record.row_type == "record_header":
                record.highlight_row = True
                record.highlight_row_type = "info"
            else:  # field_change
                record.highlight_row = False
                record.highlight_row_type = None

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH
                -- 1. Rank logs to identify the first log for each distinct record (parent or child) within a transaction.
                --    A new header is needed whenever the subject of the change (e.g., from parent to child, or child to another child) is different.
                ranked_logs AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                transaction_id,
                                model_name,
                                record_id,
                                CASE WHEN is_child_log THEN child_model_name ELSE model_name END,
                                CASE WHEN is_child_log THEN child_record_id ELSE record_id END
                            ORDER BY
                                create_date ASC, id ASC
                        ) as rn_record
                    FROM
                        oteny_audit_log_aggregated
                    WHERE
                        transaction_id IS NOT NULL AND transaction_id > 0
                ),
                -- 2. Assign a sequence to each record group within a transaction for ordering.
                record_sequencing AS (
                    SELECT
                        transaction_id,
                        model_name,
                        record_id,
                        (CASE WHEN is_child_log THEN child_model_name ELSE model_name END) AS subject_model_name,
                        (CASE WHEN is_child_log THEN child_record_id ELSE record_id END) AS subject_record_id,
                        DENSE_RANK() OVER (PARTITION BY transaction_id, model_name, record_id ORDER BY MIN(create_date), MIN(id)) * 100 AS record_display_seq
                    FROM ranked_logs
                    GROUP BY
                        transaction_id,
                        model_name,
                        record_id,
                        subject_model_name,
                        subject_record_id
                )

                -- 1. Record Headers
                SELECT
                    -- Generate a unique ID for the header row to avoid conflicts with log IDs
                    (9000000000000000000 + l.id::bigint) AS id,
                    NULL::integer AS audit_log_id,
                    l.create_date - interval '0.5 second' AS create_date,
                    l.create_uid,
                    l.transaction_id,
                    l.model_name,
                    l.model_display_name,
                    l.record_id,
                    l.record_display_name,
                    l.parent_record_display_name,
                    NULL::varchar AS field_name,
                    NULL::varchar AS field_display_name,
                    l.field_model_name,
                    l.field_model_display_name,
                    NULL::text AS old_value,
                    NULL::text AS new_value,
                    NULL::text AS old_value_display_name,
                    NULL::text AS new_value_display_name,
                    NULL::varchar AS change_type,
                    l.is_child_log,
                    l.child_model_name,
                    l.child_model_display_name,
                    l.child_record_id,
                    'record_header'::varchar AS row_type,
                    -- Caption for the record header
                    CONCAT(
                        COALESCE(l.field_model_display_name, l.model_name),
                        ' ''',
                        COALESCE(l.record_display_name, ''),
                        ''' | ',
                        COALESCE((SELECT p.name FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE u.id = l.create_uid), 'Unknown User'),
                        ' ',
                        TO_CHAR(l.create_date, 'YYYY-MM-DD HH24:MI:SS')
                    ) as caption,
                    rs.record_display_seq as display_sequence
                FROM ranked_logs l
                JOIN record_sequencing rs ON
                    l.transaction_id = rs.transaction_id AND
                    l.model_name = rs.model_name AND
                    l.record_id = rs.record_id AND
                    (CASE WHEN l.is_child_log THEN l.child_model_name ELSE l.model_name END) = rs.subject_model_name AND
                    (CASE WHEN l.is_child_log THEN l.child_record_id ELSE l.record_id END) = rs.subject_record_id
                WHERE l.rn_record = 1

                UNION ALL

                -- 2. Field Changes
                SELECT
                    l.id::bigint,
                    l.audit_log_id,
                    l.create_date,
                    l.create_uid,
                    l.transaction_id,
                    l.model_name,
                    l.model_display_name,
                    l.record_id,
                    l.record_display_name,
                    l.parent_record_display_name,
                    l.field_name,
                    l.field_display_name,
                    l.field_model_name,
                    l.field_model_display_name,
                    l.old_value,
                    l.new_value,
                    l.old_value_display_name,
                    l.new_value_display_name,
                    l.change_type,
                    l.is_child_log,
                    l.child_model_name,
                    l.child_model_display_name,
                    l.child_record_id,
                    'field_change'::varchar AS row_type,
                    -- Caption for the field change
                    CASE
                        WHEN l.change_type = 'i' THEN CONCAT('Inserted ', COALESCE(l.field_display_name, l.field_name), ' ''', COALESCE(l.new_value_display_name, l.new_value, ''), '''')
                        WHEN l.change_type = 'd' THEN CONCAT('Deleted ', COALESCE(l.field_display_name, l.field_name), ' ''', COALESCE(l.old_value_display_name, l.old_value, ''), '''')
                        ELSE CONCAT('Updated ', COALESCE(l.field_display_name, l.field_name), ' from ''', COALESCE(l.old_value_display_name, l.old_value, ''), ''' to ''', COALESCE(l.new_value_display_name, l.new_value, ''), '''')
                    END as caption,
                    -- Display sequence for field changes
                    rs.record_display_seq + (ROW_NUMBER() OVER (PARTITION BY l.transaction_id, l.model_name, l.record_id, (CASE WHEN l.is_child_log THEN l.child_model_name ELSE l.model_name END), (CASE WHEN l.is_child_log THEN l.child_record_id ELSE l.record_id END) ORDER BY l.create_date ASC, l.id ASC))
                FROM ranked_logs l
                JOIN record_sequencing rs ON
                    l.transaction_id = rs.transaction_id AND
                    l.model_name = rs.model_name AND
                    l.record_id = rs.record_id AND
                    (CASE WHEN l.is_child_log THEN l.child_model_name ELSE l.model_name END) = rs.subject_model_name AND
                    (CASE WHEN l.is_child_log THEN l.child_record_id ELSE l.record_id END) = rs.subject_record_id
            )
            """
            % self._table
        )
