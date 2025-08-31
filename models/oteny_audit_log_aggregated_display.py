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
            if record.row_type == "transaction_header":
                record.highlight_row = True
                record.highlight_row_type = "info"
            elif record.row_type == "record_header":
                record.highlight_row = True
                record.highlight_row_type = "muted"
            else:  # field_change
                record.highlight_row = False
                record.highlight_row_type = None

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH
                -- Add row numbers to base logs to identify first entry per transaction/record
                ranked_logs AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY id ASC) as rn_tx,
                        ROW_NUMBER() OVER (PARTITION BY transaction_id, model_name, record_id ORDER BY id ASC) as rn_record
                    FROM
                        oteny_audit_log
                    WHERE
                        transaction_id IS NOT NULL AND transaction_id > 0
                ),
                -- Assign a sequence number to each record group within a transaction for ordering
                record_sequencing AS (
                    SELECT
                        transaction_id,
                        model_name,
                        record_id,
                        -- Use DENSE_RANK to get a sequence for each record within a transaction, ordered by first appearance
                        DENSE_RANK() OVER (PARTITION BY transaction_id ORDER BY MIN(id)) * 100 AS record_display_seq
                    FROM ranked_logs
                    GROUP BY transaction_id, model_name, record_id
                )

                -- 1. Transaction Headers
                SELECT
                    (l.transaction_id::bigint * 1000000000000 + 1) AS id,
                    NULL::integer AS audit_log_id,
                    l.create_date - interval '1 second' AS create_date,
                    l.create_uid,
                    l.transaction_id,
                    NULL::varchar AS model_name,
                    NULL::varchar AS model_display_name,
                    NULL::integer AS record_id,
                    NULL::varchar AS record_display_name,
                    NULL::varchar AS parent_record_display_name,
                    NULL::varchar AS field_name,
                    NULL::varchar AS field_display_name,
                    NULL::varchar AS field_model_name,
                    NULL::varchar AS field_model_display_name,
                    NULL::text AS old_value,
                    NULL::text AS new_value,
                    NULL::varchar AS old_value_display_name,
                    NULL::varchar AS new_value_display_name,
                    NULL::varchar AS change_type,
                    FALSE AS is_child_log,
                    NULL::varchar AS child_model_name,
                    NULL::varchar AS child_model_display_name,
                    NULL::integer AS child_record_id,
                    'transaction_header'::varchar AS row_type,
                    CONCAT(
                        TO_CHAR(l.create_date, 'YYYY-MM-DD HH24:MI:SS'),
                        ' by ',
                        COALESCE((SELECT p.name::text FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE u.id = l.create_uid), 'Unknown User')
                    ) AS caption,
                    1 AS display_sequence
                FROM ranked_logs l
                WHERE l.rn_tx = 1

                UNION ALL

                -- 2. Record Headers
                SELECT
                    (l.transaction_id::bigint * 1000000000000 + l.record_id::bigint * 1000000 + 2) AS id,
                    NULL::integer AS audit_log_id,
                    l.create_date - interval '0.5 second' AS create_date,
                    l.create_uid,
                    l.transaction_id,
                    l.model_name,
                    (SELECT name::jsonb->>'en_US' FROM ir_model WHERE model = l.model_name) AS model_display_name,
                    l.record_id,
                    l.record_display_name::varchar,
                    NULL::varchar, NULL::varchar, NULL::varchar, NULL::varchar, NULL::varchar, NULL::text, NULL::text, NULL::varchar, NULL::varchar, NULL::varchar,
                    FALSE, NULL::varchar, NULL::varchar, NULL::integer,
                    'record_header'::varchar AS row_type,
                    CONCAT(COALESCE((SELECT name::jsonb->>'en_US' FROM ir_model WHERE model = l.model_name), l.model_name), ' ''', COALESCE(l.record_display_name::text, ''), ''''),
                    rs.record_display_seq
                FROM ranked_logs l
                JOIN record_sequencing rs ON l.transaction_id = rs.transaction_id AND l.model_name = rs.model_name AND l.record_id = rs.record_id
                WHERE l.rn_record = 1

                UNION ALL

                -- 3. Field Changes
                SELECT
                    l.id::bigint,
                    l.id AS audit_log_id,
                    l.create_date,
                    l.create_uid,
                    l.transaction_id,
                    l.model_name,
                    (SELECT name::jsonb->>'en_US' FROM ir_model WHERE model = l.model_name),
                    l.record_id,
                    l.record_display_name::varchar,
                    NULL,
                    l.field_name,
                    l.field_display_name,
                    NULL, NULL,
                    l.old_value,
                    l.new_value,
                    l.old_value_display_name,
                    l.new_value_display_name,
                    l.change_type,
                    FALSE, NULL, NULL, NULL,
                    'field_change'::varchar AS row_type,
                    CASE
                        WHEN l.change_type = 'i' THEN CONCAT('Inserted ', COALESCE(l.field_display_name, l.field_name), ' ''', COALESCE(l.new_value_display_name::text, l.new_value::text, ''), '''')
                        WHEN l.change_type = 'd' THEN CONCAT('Deleted ', COALESCE(l.field_display_name, l.field_name), ' ''', COALESCE(l.old_value_display_name::text, l.old_value::text, ''), '''')
                        ELSE CONCAT('Updated ', COALESCE(l.field_display_name, l.field_name), ' from ''', COALESCE(l.old_value_display_name::text, l.old_value::text, ''), ''' to ''', COALESCE(l.new_value_display_name::text, l.new_value::text, ''), '''')
                    END,
                    rs.record_display_seq + (ROW_NUMBER() OVER (PARTITION BY l.transaction_id, l.model_name, l.record_id ORDER BY l.id ASC))
                FROM ranked_logs l
                JOIN record_sequencing rs ON l.transaction_id = rs.transaction_id AND l.model_name = rs.model_name AND l.record_id = rs.record_id
            )
            """
            % self._table
        )
