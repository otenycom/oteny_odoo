# audit_log/models/audit_log.py
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class OtenyAuditLog(models.Model):
    _name = "oteny.audit.log"
    _description = "Oteny Audit Log"
    _order = "id desc"

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
    change_type = fields.Selection(
        [("insert", "Insert"), ("update", "Update"), ("delete", "Delete")], required=True
    )

    def _selection_record_ref(self):
        models = self.env["ir.model"].search([])
        return [(model.model, model.name) for model in models]

    @api.depends("model_name", "record_id")
    def _compute_record_ref(self):
        for log in self:
            if (
                log.model_name
                and log.record_id
                and self.env["ir.model"].search_count([("model", "=", log.model_name)])
            ):
                record = self.env[log.model_name].browse(log.record_id).exists()
                log.record_ref = record or False
            else:
                log.record_ref = False

    def _is_model_ignored(self, model_name):
        """Check if a model should be ignored by the audit log."""
        if not model_name:
            return True

        # Always ignore the audit log model itself
        if model_name == self._name:
            return True

        # Ignore models with specific prefixes
        ignored_prefixes = ["ir.", "base.", "bus.", "mail.push", "mail.tracking"]
        if any(model_name.startswith(prefix) for prefix in ignored_prefixes):
            return True

        return False

    def install_for_all_models_action(self):
        """This will be part of the post install hook for every new module, needs to be run manually for now
        goals: make an action record for all models to view their log
        """
        ACTION_CODE = """
action = {
    "name": "Audit Log",
    "type": "ir.actions.act_window",
    "res_model": "oteny.audit.log",
    "view_mode": "list,form",
    "domain": [("model_name", "=", records._name), ("record_id", "in", records.ids)],
    "target": "current",
}
"""
        models_to_install = self.env["ir.model"].search(
            [("transient", "=", False), ("model", "!=", self._name)]
        )

        for model in models_to_install:
            if self._is_model_ignored(model.model):
                continue

            _logger.info(f"Checking/creating audit log action for model {model.model}")

            action_name = f"Audit Log for {model.name}"

            module_name = "oteny_audit"
            action_xml_id = f'{module_name}.action_audit_log_{model.model.replace(".", "_")}'

            action = self.env.ref(action_xml_id, raise_if_not_found=False)

            action_vals = {
                "name": action_name,
                "model_id": model.id,
                "binding_model_id": model.id,
                "state": "code",
                "binding_view_types": "list,form",
                "code": ACTION_CODE.strip(),
            }
            if action:
                _logger.info(f"Action already exists for model {model.model}, updating it.")
                action.write(action_vals)
            else:
                _logger.info(f"Creating action for model {model.model}")
                new_action = self.env["ir.actions.server"].create(action_vals)

                self.env["ir.model.data"].create(
                    {
                        "name": action_xml_id.split(".")[1],
                        "module": module_name,
                        "res_id": new_action.id,
                        "model": "ir.actions.server",
                        "noupdate": True,
                    }
                )
                _logger.info(f"Created action for model {model.model}")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Installation Complete",
                "message": "Audit log actions have been installed for relevant models.",
                "sticky": False,
            },
        }
