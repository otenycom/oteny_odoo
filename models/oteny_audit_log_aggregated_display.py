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
    highlight_row_type = fields.Char(string="Highlight Row Type", readonly=True)
    highlight_row = fields.Boolean(string="Highlight Row", readonly=True)
    row_type = fields.Char(string="Row Type", readonly=True)
    caption = fields.Text(string="Caption", readonly=True)
    display_sequence = fields.Integer(string="Display Sequence", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH original_data AS (
                    SELECT * FROM oteny_audit_log_aggregated
                    WHERE transaction_id IS NOT NULL AND transaction_id > 0
                ),
                -- Generate transaction headers
                transaction_headers AS (
                    SELECT
                        ((transaction_id::BIGINT) * 1000000000000 + 1) AS id,
                        NULL::INTEGER AS audit_log_id,
                        MIN(od.create_date) - INTERVAL '1 second' AS create_date,
                        (ARRAY_AGG(od.create_uid ORDER BY od.create_date ASC))[1] AS create_uid,
                        transaction_id,
                        NULL::TEXT AS model_name,
                        NULL::TEXT AS model_display_name,
                        NULL::INTEGER AS record_id,
                        NULL::TEXT AS record_display_name,
                        NULL::TEXT AS parent_record_display_name,
                        NULL::TEXT AS field_name,
                        NULL::TEXT AS field_display_name,
                        NULL::TEXT AS field_model_name,
                        NULL::TEXT AS field_model_display_name,
                        NULL::TEXT AS old_value,
                        NULL::TEXT AS new_value,
                        NULL::TEXT AS old_value_display_name,
                        NULL::TEXT AS new_value_display_name,
                        NULL::TEXT AS change_type,
                        FALSE AS is_child_log,
                        NULL::TEXT AS child_model_name,
                        NULL::TEXT AS child_model_display_name,
                        NULL::INTEGER AS child_record_id,
                        'muted'::TEXT AS highlight_row_type,
                        FALSE AS highlight_row,
                        'transaction_header'::TEXT AS row_type,
                        CONCAT(
                            TO_CHAR(MIN(od.create_date), 'YYYY-MM-DD HH24:MI:SS'),
                            ' by ',
                            COALESCE((ARRAY_AGG(rp.name ORDER BY od.create_date ASC))[1], 'Unknown User')
                        ) AS caption,
                        0 AS display_sequence
                    FROM original_data od
                    LEFT JOIN res_users ru ON od.create_uid = ru.id
                    LEFT JOIN res_partner rp ON ru.partner_id = rp.id
                    GROUP BY transaction_id
                ),

                -- Generate record headers (one per unique record)
                record_headers AS (
                    SELECT
                        ((transaction_id::BIGINT) * 1000000000000 +
                         CASE WHEN is_child_log THEN child_record_id ELSE record_id END::BIGINT * 1000000 +
                         LENGTH(CASE WHEN is_child_log THEN child_model_name ELSE model_name END) * 1000 + 2) AS id,
                        NULL::INTEGER AS audit_log_id,
                        MIN(create_date) - INTERVAL '0.5 second' AS create_date,
                        MIN(create_uid) AS create_uid,
                        transaction_id,
                        CASE WHEN is_child_log THEN child_model_name ELSE model_name END AS model_name,
                        CASE WHEN is_child_log THEN child_model_display_name ELSE model_display_name END AS model_display_name,
                        CASE WHEN is_child_log THEN child_record_id ELSE record_id END AS record_id,
                        CASE WHEN is_child_log THEN record_display_name ELSE record_display_name END AS record_display_name,
                        parent_record_display_name,
                        NULL::TEXT AS field_name,
                        NULL::TEXT AS field_display_name,
                        NULL::TEXT AS field_model_name,
                        NULL::TEXT AS field_model_display_name,
                        NULL::TEXT AS old_value,
                        NULL::TEXT AS new_value,
                        NULL::TEXT AS old_value_display_name,
                        NULL::TEXT AS new_value_display_name,
                        NULL::TEXT AS change_type,
                        is_child_log,
                        CASE WHEN is_child_log THEN child_model_name ELSE NULL END AS child_model_name,
                        CASE WHEN is_child_log THEN child_model_display_name ELSE NULL END AS child_model_display_name,
                        CASE WHEN is_child_log THEN child_record_id ELSE NULL END AS child_record_id,
                        'muted'::TEXT AS highlight_row_type,
                        FALSE AS highlight_row,
                        'record_header'::TEXT AS row_type,
                        CASE
                            WHEN is_child_log THEN
                                CONCAT(
                                    COALESCE(child_model_display_name, child_model_name, 'Unknown Model'),
                                    ' ',
                                    COALESCE(CASE WHEN is_child_log THEN record_display_name ELSE record_display_name END, 'Unknown Child Record'),
                                    ' on ',
                                    COALESCE(model_display_name, model_name, 'Unknown Parent Model'),
                                    ' ',
                                    COALESCE(parent_record_display_name, 'Unknown Parent Record')
                                )
                            ELSE
                                CONCAT(
                                    COALESCE(model_display_name, model_name, 'Unknown Model'),
                                    ' ',
                                    COALESCE(CASE WHEN is_child_log THEN record_display_name ELSE record_display_name END, 'Unknown Record')
                                )
                        END AS caption,
                        -- Use ROW_NUMBER to assign proper display sequences
                        ROW_NUMBER() OVER (
                            PARTITION BY transaction_id
                            ORDER BY
                                CASE WHEN is_child_log THEN child_record_id ELSE record_id END,
                                CASE WHEN is_child_log THEN child_model_name ELSE model_name END
                        ) * 100 + 1 AS display_sequence
                    FROM original_data
                    GROUP BY transaction_id,
                             CASE WHEN is_child_log THEN child_record_id ELSE record_id END,
                             CASE WHEN is_child_log THEN child_model_name ELSE model_name END,
                             CASE WHEN is_child_log THEN child_model_display_name ELSE model_display_name END,
                             CASE WHEN is_child_log THEN record_display_name ELSE record_display_name END,
                             is_child_log, child_model_name, child_model_display_name, child_record_id,
                             model_name, model_display_name, record_id, parent_record_display_name
                ),

                -- Generate field changes with matching display sequences
                field_changes AS (
                    SELECT
                        od.id::BIGINT,
                        od.audit_log_id,
                        od.create_date,
                        od.create_uid,
                        od.transaction_id,
                        od.model_name,
                        od.model_display_name,
                        od.record_id,
                        od.record_display_name,
                        od.parent_record_display_name,
                        od.field_name,
                        od.field_display_name,
                        od.field_model_name,
                        od.field_model_display_name,
                        od.old_value,
                        od.new_value,
                        od.old_value_display_name,
                        od.new_value_display_name,
                        od.change_type,
                        od.is_child_log,
                        od.child_model_name,
                        od.child_model_display_name,
                        od.child_record_id,
                        od.highlight_row_type,
                        od.highlight_row,
                        'field_change'::TEXT AS row_type,
                        CASE
                            WHEN od.change_type = 'i' THEN
                                CONCAT(
                                    'Insert ',
                                    COALESCE(od.field_display_name, od.field_name, 'Unknown Field'),
                                    ' to ',
                                    COALESCE(od.new_value_display_name, od.new_value, '')
                                )
                            WHEN od.change_type = 'd' THEN
                                CONCAT(
                                    'Delete ',
                                    COALESCE(od.field_display_name, od.field_name, 'Unknown Field'),
                                    ' (was ',
                                    COALESCE(od.old_value_display_name, od.old_value, ''),
                                    ')'
                                )
                            ELSE -- 'u' for update
                                CONCAT(
                                    'Update ',
                                    COALESCE(od.field_display_name, od.field_name, 'Unknown Field'),
                                    ' from ',
                                    COALESCE(od.old_value_display_name, od.old_value, ''),
                                    ' to ',
                                    COALESCE(od.new_value_display_name, od.new_value, '')
                                )
                        END AS caption,
                        -- Calculate display sequence to match record headers
                        rh.display_sequence + ROW_NUMBER() OVER (
                            PARTITION BY od.transaction_id,
                                         CASE WHEN od.is_child_log THEN od.child_record_id ELSE od.record_id END,
                                         CASE WHEN od.is_child_log THEN od.child_model_name ELSE od.model_name END
                            ORDER BY od.create_date DESC, od.id DESC
                        ) AS display_sequence
                    FROM original_data od
                    JOIN record_headers rh ON
                        od.transaction_id = rh.transaction_id AND
                        CASE WHEN od.is_child_log THEN od.child_record_id ELSE od.record_id END = rh.record_id AND
                        CASE WHEN od.is_child_log THEN od.child_model_name ELSE od.model_name END = rh.model_name
                )
                -- Combine all rows
                SELECT * FROM transaction_headers
                UNION ALL
                SELECT * FROM record_headers
                UNION ALL
                SELECT * FROM field_changes
                ORDER BY transaction_id DESC, display_sequence ASC, create_date DESC, id DESC
            )"""
            % self._table
        )
