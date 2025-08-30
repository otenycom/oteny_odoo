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
        """
        ACTION_CODE = """
action = {
    "name": "Audit Log",
    "type": "ir.actions.act_window",
    "res_model": "oteny.audit.log.aggregated",
    "view_mode": "list,form",
    "domain": [("model_name", "=", records._name), ("record_id", "in", records.ids)],
    "target": "current",
}
"""
        # Get all non-transient models except ourselves
        all_models = self.env["ir.model"].search([("transient", "=", False), ("model", "!=", self._name)])

        module_name = "oteny_audit"
        actions_created = 0
        actions_updated = 0
        actions_removed = 0

        _logger.info(f"Starting audit log action setup for {len(all_models)} models")

        # Track which models should have audit actions
        models_with_audit = set()

        for model in all_models:
            if self._is_audit_ignored(model.model):
                continue

            models_with_audit.add(model.model)
            action_xml_id = f'{module_name}.action_audit_log_{model.model.replace(".", "_")}'

            # Check if action already exists
            existing_action = self.env.ref(action_xml_id, raise_if_not_found=False)

            action_name = f"Audit Log for {model.name}"
            action_vals = {
                "name": action_name,
                "model_id": model.id,
                "binding_model_id": model.id,
                "state": "code",
                "binding_view_types": "list,form",
                "code": ACTION_CODE.strip(),
            }

            if existing_action:
                _logger.debug(f"Action already exists for model {model.model}, updating it.")
                existing_action.write(action_vals)
                actions_updated += 1
            else:
                new_action = self.env["ir.actions.server"].create(action_vals)

                # Create XML ID for the action
                self.env["ir.model.data"].create(
                    {
                        "name": action_xml_id.split(".")[1],
                        "module": module_name,
                        "res_id": new_action.id,
                        "model": "ir.actions.server",
                        "noupdate": True,
                    }
                )
                actions_created += 1

        # Remove actions for models that are now ignored
        # Find all existing audit log actions for this module
        existing_xml_ids = self.env["ir.model.data"].search(
            [
                ("module", "=", module_name),
                ("name", "like", "action_audit_log_%"),
                ("model", "=", "ir.actions.server"),
            ]
        )

        for xml_id_record in existing_xml_ids:
            # Extract model name from XML ID
            xml_id_name = xml_id_record.name
            if xml_id_name.startswith("action_audit_log_"):
                model_name_from_xml = xml_id_name[len("action_audit_log_") :].replace("_", ".")

                # Check if this model should still have an audit action
                if model_name_from_xml not in models_with_audit:
                    # This model is now ignored, remove the action
                    action_to_remove = self.env["ir.actions.server"].browse(xml_id_record.res_id)
                    if action_to_remove.exists():
                        _logger.debug(f"Removing audit action for ignored model {model_name_from_xml}")
                        action_to_remove.unlink()
                        actions_removed += 1

        # Log all created, updated, and removed actions in a single message
        _logger.info(
            f"Audit log action setup complete: {actions_created} created, {actions_updated} updated, {actions_removed} removed"
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Audit Log Setup Complete",
                "message": f"Created {actions_created} new audit actions, updated {actions_updated} existing ones.",
                "sticky": False,
            },
        }
