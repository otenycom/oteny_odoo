# audit_log/models/audit_log.py
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class OtenyAuditLog(models.Model):
    _name = "oteny.audit.log"
    _description = "Oteny Audit Log"
    _order = "id desc"

    # Predefined parent references or id-keys for well-known models
    _model_parent_keys = {
        "mail.message": "model,res_id",
        "ir.attachment": "res_model,res_id",
        "mail.followers": "res_model,res_id",
        "res.partner": "parent_id",
    }

    transaction_id = fields.Integer(required=False, string="Transaction ID")
    model_name = fields.Char(required=True)
    record_id = fields.Integer(required=True, string="Record ID")
    record_ref = fields.Reference(
        string="Record Link",
        selection="_selection_record_ref",
        compute="_compute_record_ref",
        readonly=True,
    )
    record_display_name = fields.Char(string="Record Name")
    field_name = fields.Char(required=True, string="Field Raw Name")
    field_display_name = fields.Char(string="Field")
    old_value = fields.Text(string="Old Value Raw")
    new_value = fields.Text(string="New Value Raw")
    old_value_display_name = fields.Char(string="Old Value")
    new_value_display_name = fields.Char(string="New Value")
    change_type = fields.Selection([("i", "Insert"), ("u", "Update"), ("d", "Delete")], required=True)

    def _selection_record_ref(self):
        models = self.env["ir.model"].search([])
        return [(model.model, model.name) for model in models]

    @api.depends("model_name", "record_id")
    def _compute_record_ref(self):
        for log in self:
            if log.model_name and log.record_id and log.model_name in self.env:
                record = self.env[log.model_name].browse(log.record_id).exists()
                log.record_ref = f"{log.model_name},{record.id}" if record else False
            else:
                log.record_ref = False

    def _is_audit_ignored(self, model_name):
        """Check if a model should be ignored by the audit log."""
        if self.env.context.get("oteny_audit_ignore", False):
            return True

        model_class = self.env[model_name]
        if hasattr(model_class, "_oteny_audit_ignore"):
            return model_class._oteny_audit_ignore

        # Ignore TransientModel models (wizards) by default
        if getattr(model_class, "_transient", False):
            return True

        # Ignore system models by default, can be overridden by _oteny_audit_ignore in the model
        ignored_model_prefixes = [
            "oteny.audit",
            "ir.ui.view",
            "ir.model.data",
            "bus.",
            "mail.push",
            "mail.tracking",
            "res.device.log",
        ]
        if any(model_name.startswith(prefix) for prefix in ignored_model_prefixes):
            return True

        return False

    def install_for_all_models_action(self):
        """Create audit log actions for all models that don't already have them.
        This will be called automatically when modules are installed.
        Creates one action per model for the raw aggregated view.
        """
        # Get all non-transient models except ourselves
        all_models = self.env["ir.model"].search([("transient", "=", False), ("model", "!=", self._name)])
        eligible_models = all_models.filtered(lambda m: not self._is_audit_ignored(m.model))

        _logger.info(f"Starting audit log action setup for {len(eligible_models)} models")

        # Process actions in batches for better performance and readability
        actions_created, actions_updated = self._batch_process_actions(eligible_models)

        # Clean up actions for models that are no longer eligible
        actions_removed = self._cleanup_obsolete_actions(eligible_models)

        # Log summary
        total_models = len(eligible_models)
        _logger.info(
            f"Audit log action setup complete: {actions_created} created, {actions_updated} updated, {actions_removed} removed "
            f"({total_models} models processed)"
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Audit Log Setup Complete",
                "message": f"Created {actions_created} new audit actions ({total_models} models), updated {actions_updated} existing ones.",
                "sticky": False,
            },
        }

    def _get_action_code(self):
        """Get the action code template for the audit log action."""
        ACTION_CODE = """
action = {
    "name": "Audit Log",
    "type": "ir.actions.act_window",
    "res_model": "oteny.audit.log.aggregated.display", #.aggregated.display
    "view_mode": "list",
    "domain": [("model_name", "=", records._name), ("record_id", "in", records.ids)],
    "target": "current",
}
"""
        return ACTION_CODE.strip()

    def _batch_process_actions(self, models):
        """Process action creation/updates in batches for better performance."""
        action_code = self._get_action_code()
        module_name = "oteny_audit"

        actions_data = []

        for model in models:
            xml_id = f"{module_name}.action_audit_log_{model.model.replace('.', '_')}"
            actions_data.append(
                {
                    "xml_id": xml_id,
                    "name": f"Audit Log for {model.name}",
                    "model_id": model.id,
                    "code": action_code,
                }
            )

        # Process actions
        created, updated = self._process_action_batch(actions_data, "audit")

        return created, updated

    def _process_action_batch(self, actions_data, action_type):
        """Process a batch of actions, creating new ones and updating existing ones."""
        module_name = "oteny_audit"
        actions_created = 0
        actions_updated = 0

        # Check which actions already exist
        xml_ids = [data["xml_id"] for data in actions_data]
        existing_refs = {}
        for xml_id in xml_ids:
            existing_ref = self.env.ref(xml_id, raise_if_not_found=False)
            if existing_ref:
                existing_refs[xml_id] = existing_ref

        # Process each action
        for action_data in actions_data:
            xml_id = action_data["xml_id"]
            action_vals = {
                "name": action_data["name"],
                "model_id": action_data["model_id"],
                "binding_model_id": action_data["model_id"],
                "state": "code",
                "binding_view_types": "list,form",
                "code": action_data["code"],
            }

            if xml_id in existing_refs:
                # Update existing action
                _logger.debug(f"{action_type.title()} action already exists for model, updating it.")
                existing_refs[xml_id].write(action_vals)
                actions_updated += 1
            else:
                # Create new action
                new_action = self.env["ir.actions.server"].create(action_vals)
                self.env["ir.model.data"].create(
                    {
                        "name": xml_id.split(".")[1],
                        "module": module_name,
                        "res_id": new_action.id,
                        "model": "ir.actions.server",
                        "noupdate": True,
                    }
                )
                actions_created += 1

        return actions_created, actions_updated

    def _cleanup_obsolete_actions(self, eligible_models):
        """Remove actions for models that are no longer eligible for auditing."""
        module_name = "oteny_audit"
        actions_removed = 0

        # Build a set of expected XML IDs for all eligible models
        expected_xml_ids = {
            f"{module_name}.action_audit_log_{model.model.replace('.', '_')}" for model in eligible_models
        }

        # Find all existing audit log actions for this module
        existing_xml_id_records = self.env["ir.model.data"].search(
            [
                ("module", "=", module_name),
                ("name", "like", "action_audit_log_%"),
                ("model", "=", "ir.actions.server"),
            ]
        )

        for xml_id_record in existing_xml_id_records:
            full_xml_id = f"{xml_id_record.module}.{xml_id_record.name}"
            if full_xml_id not in expected_xml_ids:
                action_to_remove = self.env["ir.actions.server"].browse(xml_id_record.res_id)
                if action_to_remove.exists():
                    _logger.debug(f"Removing obsolete audit action with XML ID {full_xml_id}")
                    xml_id_record.unlink()
                    action_to_remove.unlink()
                    actions_removed += 1

        return actions_removed

    def _get_cleanup_config(self):
        """Get cleanup configuration from system parameters."""
        get_param = self.env["ir.config_parameter"].sudo().get_param
        return {
            "enabled": get_param("oteny_audit.cleanup_enabled", "True").lower() == "true",
            "retention_days": int(get_param("oteny_audit.retention_days", "180")),
            "batch_size": int(get_param("oteny_audit.batch_size", "5000")),
            "pause_seconds": int(get_param("oteny_audit.cleanup_pause_seconds", "1")),
        }

    def cleanup_old_audit_logs(self):
        """
        Clean up old audit log records based on configuration.
        This method is called by the cron job.

        Transaction Strategy:
        - Commits after each batch to free memory and prevent timeouts
        - Handles large datasets efficiently by processing in chunks
        - Includes error handling for commit operations
        """
        config = self._get_cleanup_config()

        if not config["enabled"]:
            _logger.info("Audit log cleanup is disabled")
            return

        # Calculate the cutoff date using Odoo's UTC time
        from odoo.fields import Datetime
        from datetime import timedelta

        cutoff_date = Datetime.now() - timedelta(days=config["retention_days"])

        _logger.info(
            f"Starting audit log cleanup. Deleting records older than {config['retention_days']} days "
            f"(before {cutoff_date.date()}). Batch size: {config['batch_size']}, "
            f"Pause: {config['pause_seconds']} seconds"
        )

        # Get total count of records to be deleted
        old_logs_count = self.search_count([("create_date", "<", cutoff_date)])
        _logger.info(f"Found {old_logs_count} audit log records to delete")

        if old_logs_count == 0:
            _logger.info("No old audit log records to delete")
            return

        deleted_count = 0
        import time

        # Delete in batches
        while True:
            # Find batch of records to delete
            old_logs = self.search(
                [("create_date", "<", cutoff_date)], limit=config["batch_size"], order="id"
            )

            if not old_logs:
                break

            batch_count = len(old_logs)
            _logger.info(f"Deleting batch of {batch_count} audit log records...")

            # Delete the batch
            old_logs.unlink()

            # Commit the transaction after each batch to free up memory and avoid timeouts
            try:
                self.env.cr.commit()
                _logger.debug(f"Committed batch deletion of {batch_count} records")
            except Exception as e:
                _logger.warning(f"Failed to commit batch deletion: {e}")

            deleted_count += batch_count
            _logger.info(f"Deleted {deleted_count}/{old_logs_count} audit log records")

            # Check if there are more records to delete
            remaining_count = self.search_count([("create_date", "<", cutoff_date)])
            if remaining_count == 0:
                break

            # Pause between batches to allow DB to process
            if config["pause_seconds"] > 0:
                _logger.info(f"Pausing for {config['pause_seconds']} seconds...")
                time.sleep(config["pause_seconds"])

        _logger.info(f"Audit log cleanup completed. Deleted {deleted_count} records")

        # Also clean up parent references for deleted logs
        _logger.info("Cleaning up orphaned parent references...")
        self.env.cr.execute(
            """
            DELETE FROM oteny_audit_log_parent_ref
            WHERE audit_log_id NOT IN (SELECT id FROM oteny_audit_log)
        """
        )
        orphaned_refs_count = self.env.cr.rowcount
        _logger.info(f"Deleted {orphaned_refs_count} orphaned parent reference records")

        # Commit the final cleanup
        try:
            self.env.cr.commit()
            _logger.debug("Committed final cleanup of orphaned references")
        except Exception as e:
            _logger.warning(f"Failed to commit final cleanup: {e}")

        return {
            "deleted_logs": deleted_count,
            "deleted_refs": orphaned_refs_count,
            "cutoff_date": cutoff_date.date(),
        }
