from odoo import models, Command, _
from odoo.exceptions import UserError


class ServiceNewWizard(models.TransientModel):
    _name = "riverflow.start.service"
    _inherit = "riverflow.start.wizard"
    _description = "Service Start Transition selection Wizard"

    _workflow_model = "riverflow.service"

    def _add_template_start_transitions(self, transition_buttons, defaults_context):
        # fetch all services with is_root_a_template=True, sorted by default order (respecting the tree structure)
        template_services = self.env["riverflow.service"].search(
            [("is_root_a_template", "=", True)]
        )

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

    def _create_service_from_template(self, template_service, parent_id=False):
        """Create a new service based on a template service.

        Args:
            template_service: The template service record to clone from
            parent_id: Optional parent service ID for the new service

        Returns:
            The newly created service record
        """
        vals = {
            "name": template_service.name,
            "workflow_id": template_service.workflow_id.id,
            "state_id": template_service.state_id.id,
            "use_project_deadline_from": template_service.use_project_deadline_from,
            "days_relative_to_project": template_service.days_relative_to_project,
            "is_this_a_template": False,
            "email_template_id": template_service.email_template_id.id,
            "add_operator_as_recipient": template_service.add_operator_as_recipient,
            "tag_ids": [
                Command.link(tag_id) for tag_id in template_service.tag_ids.ids
            ],
        }
        if parent_id:
            vals["parent_id"] = parent_id

        new_service = (
            self.env["riverflow.service"]
            .with_context(context={"mail_create_nosubscribe": True})
            .create(vals)
        )

        # Clone notes (comments) from template
        template_notes = self.env["mail.message"].search(
            [
                ("model", "=", "riverflow.service"),
                ("res_id", "=", template_service.id),
                ("message_type", "=", "comment"),
                ("subtype_id", "=", self.env.ref("mail.mt_note").id),
            ]
        )

        for note in template_notes:
            # First clone the attachments
            new_attachment_ids = []
            if note.attachment_ids:
                for attachment in note.attachment_ids:
                    new_attachment = attachment.copy(
                        {
                            "res_id": new_service.id,
                            "res_model": "riverflow.service",
                        }
                    )
                    new_attachment_ids.append(new_attachment.id)

            self.env["mail.message"].sudo().create(
                {
                    "subject": note.subject,
                    "body": note.body,
                    "message_type": note.message_type,
                    "model": "riverflow.service",
                    "res_id": new_service.id,
                    "subtype_id": note.subtype_id.id,
                    "author_id": note.author_id.id,
                    "email_from": note.email_from,
                    "create_uid": note.create_uid.id,
                    "parent_id": note.parent_id.id,
                    "date": note.date,
                    "starred": note.starred,
                    "starred_partner_ids": [(6, 0, note.starred_partner_ids.ids)],
                    "attachment_ids": [(6, 0, new_attachment_ids)],
                }
            )

        return new_service

    def action_apply_template(self):
        self.ensure_one()

        template_service_id = self.env.context.get("template_service_id")
        template_service = self.env["riverflow.service"].browse(template_service_id)
        if not template_service:
            raise UserError(_("No template service selected."))

        # Create main service from template
        new_service = self._create_service_from_template(template_service)

        # Clone children recursively
        def clone_children(template, parent):
            for child in template.child_ids:
                new_child = self._create_service_from_template(child, parent.id)
                clone_children(child, new_child)

        clone_children(template_service, new_service)

        return {
            "type": "ir.actions.act_window",
            "res_model": "riverflow.service",
            "res_id": new_service.id,
            "view_mode": "form",
            "target": "current",
        }
