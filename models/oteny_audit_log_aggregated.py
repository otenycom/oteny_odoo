from odoo import api, fields, models, tools
import markupsafe
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class OtenyAuditLogAggregated(models.Model):
    _name = "oteny.audit.log.aggregated"
    _description = "Aggregated Audit Log (including children)"
    _auto = False
    _order = "id DESC"

    audit_log_id = fields.Many2one("oteny.audit.log", string="Audit Log", readonly=True)
    parent_record_display_name = fields.Char(string="Parent Record", readonly=True)

    # --- Fields from oteny.audit.log ---
    transaction_id = fields.Integer(readonly=True, string="Transaction ID")
    model_name = fields.Char(readonly=True, string="Parent Model Name")
    model_display_name = fields.Char(
        string="Parent Model",
        readonly=True,
    )
    record_id = fields.Integer(readonly=True, string="Record ID")
    record_ref = fields.Reference(
        string="Record Link",
        selection="_selection_record_ref",
        compute="_compute_record_ref",
        readonly=True,
    )
    record_display_name = fields.Char(string="Record", readonly=True)
    field_name = fields.Char(readonly=True, string="Field Raw Name")
    field_display_name = fields.Char(string="Field", readonly=True)
    field_model_name = fields.Char(string="Model Name", readonly=True)
    field_model_display_name = fields.Char(
        string="Model",
        readonly=True,
    )
    old_value = fields.Text(string="Old Value Raw", readonly=True)
    new_value = fields.Text(string="New Value Raw", readonly=True)
    old_value_display_name = fields.Char(string="Old Value", readonly=True)
    new_value_display_name = fields.Char(string="New Value", readonly=True)
    change_type = fields.Selection(
        [("i", "Insert"), ("u", "Update"), ("d", "Delete")],
        readonly=True,
        string="Change",
    )
    create_date = fields.Datetime(string="Timestamp", readonly=True)
    create_uid = fields.Many2one("res.users", string="User", readonly=True)

    # --- Fields to distinguish parent/child logs ---
    is_child_log = fields.Boolean(string="Is Child Log?", readonly=True)
    child_model_name = fields.Char(string="Child Model", readonly=True)
    child_model_display_name = fields.Char(
        string="Child Model Display Name",
        readonly=True,
    )
    child_record_id = fields.Integer(string="Child Record ID", readonly=True)
    child_record_ref = fields.Reference(
        string="Child Record Link",
        selection="_selection_record_ref",
        compute="_compute_child_record_ref",
        readonly=True,
    )
    caption = fields.Html(string="Caption", readonly=True, compute="_compute_caption")

    def _compute_caption(self):
        # self can be ordered by the user in the view. We need to respect that order to check the 'previous' record.
        log_list = list(self)
        change_type_verbs = {"i": "Insert", "u": "Update", "d": "Delete"}
        date_format = self.env["riverflow.service"].DATETIME_FORMAT
        for i, log in enumerate(log_list):
            caption_parts = []

            # Determine if a header is needed for this log entry.
            # A header is shown for the first item in a batch, or when the record being audited changes,
            # or when the transaction ID changes.
            show_header = False
            if i == 0:
                show_header = True
            else:
                prev_log = log_list[i - 1]

                # The 'record' is defined by its model and ID.
                # For child logs, this is the child's model/ID. For parent logs, it's the parent's.
                current_record_key = (
                    (log.field_model_name, log.child_record_id, log.change_type)
                    if log.is_child_log
                    else (log.model_name, log.record_id, log.change_type)
                )
                prev_record_key = (
                    (prev_log.field_model_name, prev_log.child_record_id, prev_log.change_type)
                    if prev_log.is_child_log
                    else (prev_log.model_name, prev_log.record_id, prev_log.change_type)
                )

                if current_record_key != prev_record_key or log.transaction_id != prev_log.transaction_id:
                    show_header = True

            if show_header:
                # The header displays info about the record being changed.
                # For child logs, record_display_name is the child's name, and field_model_display_name is the child model.
                # For direct logs, record_display_name is the record's name, and field_model_display_name is its model.
                model_display = markupsafe.escape(log.field_model_display_name or "")
                record_display = markupsafe.escape(log.record_display_name or "")
                verb = change_type_verbs.get(log.change_type, "changed")
                user_display = markupsafe.escape(log.create_uid.name if log.create_uid else "")

                date_display = fields.Datetime.context_timestamp(self, log.create_date).strftime(date_format)

                # Add color styling to the record name for better visual distinction
                # Uses CSS classes for dark mode compliance
                styled_record_display = f'<span class="oteny-audit-record-header">{record_display}</span>'
                header_str = f"{verb} {model_display} {styled_record_display} by <b>{user_display}</b> on {date_display}"
                caption_parts.append(f"<div>{header_str}</div>")

            # The second part of the caption describes the specific field change.
            change_type = log.change_type
            field_name = markupsafe.escape(log.field_display_name or "")

            # Determine if the field contains HTML content
            is_html_field = self._is_html_field(log)

            if change_type == "i":
                new_val = self._format_field_value(log.new_value_display_name or "", is_html_field)
                field_change_str = f"Set <b>{field_name}</b> to <b>{new_val}</b>"
            elif change_type == "u":
                old_val = self._format_field_value(log.old_value_display_name or "", is_html_field)
                new_val = self._format_field_value(log.new_value_display_name or "", is_html_field)
                field_change_str = (
                    f"Updated <b>{field_name}</b> from '<b>{old_val}</b>' to '<b>{new_val}</b>'"
                )
            elif change_type == "d":
                old_val = self._format_field_value(log.old_value_display_name or "", is_html_field)
                field_change_str = f"<b>{field_name}</b> was <b>{old_val}</b>"
            else:
                field_change_str = ""

            if field_change_str:
                caption_parts.append(f"<div class='ms-4'>{field_change_str}</div>")

            log.caption = markupsafe.Markup("".join(caption_parts))

        # Ensure any records not processed (e.g. empty self) have a value
        for log in self:
            if log.caption is False:
                log.caption = ""

    def _is_html_field(self, log):
        """Check if the field being audited is an HTML field."""
        try:
            # Get the model where the field is defined
            model_name = log.field_model_name
            field_name = log.field_name

            if not model_name or not field_name:
                return False

            # Get the model class
            if model_name not in self.env:
                return False
            model_class = self.env[model_name]
            field = model_class._fields.get(field_name, False)
            if not field:
                return False

            # Check if it's an HTML field
            return field.type == "html"

        except Exception as e:
            # If anything goes wrong, default to safe escaping
            _logger.warning(
                "Could not determine if field %s.%s is an HTML field. Error: %s",
                log.field_model_name,
                log.field_name,
                e,
            )
            return False

    def _format_field_value(self, value, is_html_field):
        """Format field value for display, either as HTML or escaped text."""
        if not value:
            return ""

        # Convert date/datetime values from UTC to local time
        converted_value = self._convert_date_value_to_local(value)

        if is_html_field:
            wrapped_value = f'<div class="oteny-audit-html-field">{converted_value}</div>'
            # Mark as safe to prevent double-escaping
            return markupsafe.Markup(wrapped_value)
        else:
            # For non-HTML fields, escape to prevent XSS
            return markupsafe.escape(converted_value)

    def _convert_date_value_to_local(self, value):
        """Convert date/datetime string values from UTC to local time."""
        if not value or not isinstance(value, str):
            return value

        try:
            # Try to parse as datetime first (with timezone info)
            # Common Odoo datetime formats: "2023-12-01 10:30:00+00:00" or "2023-12-01 10:30:00"
            if " " in value and ("+" in value or "-" in value and value.count("-") >= 2):
                # Looks like a datetime string
                try:
                    # Parse with timezone info if available
                    dt = fields.Datetime.to_datetime(value)
                    # Convert to local time using the same approach as date_display
                    local_dt = fields.Datetime.context_timestamp(self, dt)
                    datetime_format = self.env["riverflow.service"].DATETIME_FORMAT
                    return local_dt.strftime(datetime_format)
                except (ValueError, TypeError):
                    pass

            if "-" in value and len(value.split("-")) == 3 and " " not in value:
                try:
                    date = fields.Date.to_date(value)
                    date_format = self.env["riverflow.service"].DATE_FORMAT
                    return date.strftime(date_format)
                except (ValueError, TypeError):
                    pass

        except Exception:
            # If conversion fails, return original value
            pass

        # Return original value if not a date/datetime or conversion failed
        return value

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

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                -- Simplified view using the new ref structure
                -- No complex CTEs, no window functions, just simple JOINs
                SELECT 
                    ref.id,
                    ref.audit_log_id,
                    log.create_date,
                    log.create_uid,
                    log.transaction_id,
                    
                    -- Target record info (what's being viewed)
                    ref.target_model_name as model_name,
                    COALESCE(im_target.name->>'en_US', ref.target_model_name) AS model_display_name,
                    ref.target_record_id as record_id,
                    ref.target_display_name as record_display_name,
                    
                    -- Parent record info (for child logs)
                    CASE WHEN NOT ref.is_direct 
                         THEN ref.target_display_name 
                         ELSE log.record_display_name 
                    END as parent_record_display_name,
                    
                    -- Field change details
                    log.field_name,
                    log.field_display_name,
                    log.model_name as field_model_name,
                    COALESCE(im_field.name->>'en_US', log.model_name) AS field_model_display_name,
                    log.old_value,
                    log.new_value,
                    log.old_value_display_name,
                    log.new_value_display_name,
                    log.change_type,
                    
                    -- Child log indicators
                    NOT ref.is_direct as is_child_log,
                    CASE WHEN NOT ref.is_direct THEN log.model_name ELSE NULL END as child_model_name,
                    CASE WHEN NOT ref.is_direct 
                         THEN COALESCE(im_child.name->>'en_US', log.model_name) 
                         ELSE NULL 
                    END as child_model_display_name,
                    CASE WHEN NOT ref.is_direct THEN log.record_id ELSE NULL END as child_record_id
                    
                FROM oteny_audit_log_ref ref
                JOIN oteny_audit_log log ON ref.audit_log_id = log.id
                LEFT JOIN ir_model im_target ON ref.target_model_name = im_target.model
                LEFT JOIN ir_model im_field ON log.model_name = im_field.model
                LEFT JOIN ir_model im_child ON (NOT ref.is_direct AND log.model_name = im_child.model)
            )
        """
            % self._table
        )
