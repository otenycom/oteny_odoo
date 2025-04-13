from odoo import models, Command, _
from odoo.exceptions import UserError


class ServiceNewWizard(models.TransientModel):
    _name = "riverflow.start.service"
    _inherit = "riverflow.start.wizard"
    _description = "Service Start Transition selection Wizard"

    _workflow_model = "riverflow.service"

    def _add_template_start_transitions(self, transition_buttons, defaults_context):
        # fetch all services with is_root_a_template=True, sorted by default order (respecting the tree structure)
        template_services = self.env["riverflow.service"].search([("is_root_a_template", "=", True)])

        index = 0
        for template_service in template_services:
            button_context = defaults_context.copy()
            button_context["template_service_id"] = template_service.id
            icon = template_service.workflow_id.icon or "plus"

            transition_buttons["buttons"].append(
                {
                    "index": index,
                    "is_template": True,
                    "indent_level": template_service.indent_level,
                    "icon": icon,
                    "caption": f"{template_service.indented_name}",
                    "help": "",
                    "action": "action_apply_template",
                    "context": button_context,
                }
            )
            index += 1

    def action_apply_template(self):
        self.ensure_one()

        template_service_id = self.env.context.get("template_service_id")

        # Read the deadline from the client-side input field
        project_deadline = self.env.context.get("default_project_deadline")
        if not project_deadline:
            raise UserError(_("You must set the Deadline"))

        new_service = self.env["riverflow.service"]._create_service_from_template(
            template_service_id, project_deadline
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "riverflow.service",
            "res_id": new_service.id,
            "view_mode": "form",
            "target": "current",
        }
