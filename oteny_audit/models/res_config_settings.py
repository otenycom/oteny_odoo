from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Audit log cleanup settings
    audit_log_cleanup_enabled = fields.Boolean(
        string="Enable Audit Log Cleanup",
        config_parameter="oteny_audit.cleanup_enabled",
        default=True,
        help="Enable automatic cleanup of old audit log records",
    )

    audit_log_retention_days = fields.Integer(
        string="Audit Log Retention (Days)",
        config_parameter="oteny_audit.retention_days",
        default=180,
        help="Number of days to keep audit log records before deletion",
    )

    audit_log_batch_size = fields.Integer(
        string="Cleanup Batch Size",
        config_parameter="oteny_audit.batch_size",
        default=5000,
        help="Number of records to delete in each batch during cleanup",
    )

    audit_log_cleanup_pause_seconds = fields.Integer(
        string="Cleanup Pause (Seconds)",
        config_parameter="oteny_audit.cleanup_pause_seconds",
        default=5,
        help="Number of seconds to pause between cleanup batches",
    )

    audit_log_cleanup_cron_time = fields.Char(
        string="Cleanup Cron Time",
        config_parameter="oteny_audit.cleanup_cron_time",
        default="0 2 * * *",  # 2 AM every day
        help="Cron expression for when to run the cleanup (default: 0 2 * * * = 2 AM daily)",
    )
