# audit_log/models/audit_log.py
from odoo import fields, models
import logging

_logger = logging.getLogger(__name__)


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
            if model.model.startswith("ir.") or model.model.startswith("base."):
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
