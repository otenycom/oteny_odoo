from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError


class TransitionWizard(models.AbstractModel):
    _name = "riverflow.transition.wizard"
    _description = "Transition action base Wizard"

    _workflow_model = "definedInDerivedClass"

    transition_id = fields.Many2one("riverflow.transition", "Transition")
    transition_description = fields.Text("Description")
    # record_ids = fields.Many2many(_workflow_model)

    def action_save(self):
        for wizard in self:
            transition = wizard.transition_id

            if not transition:
                raise exceptions.ValidationError("Workflow Transition not specified")

            services = wizard.record_ids

            createNewRecord = len(wizard.record_ids) == 0
            if createNewRecord:
                new_record = self.env[self._workflow_model].new(
                    {
                        "workflow_id": transition.workflow_id.id,
                    }
                )

                services = [new_record]

                action = {
                    "type": "ir.actions.act_window",
                    "res_model": self._workflow_model,
                    "res_id": new_record.id,  # NewId value, will be updated below
                    # "views": [(self.env.ref("riverflow.view_service_form").id, "form")],
                    "view_mode": "form",
                    "target": "current",
                    "context": {},
                }
            else:
                action = {"type": "ir.actions.act_window_close"}

            # Set the property values
            for service in services:
                self.set_property_values(service)
                service.state_id = transition.to_state_id.id

            if createNewRecord:
                # Save the record to the database, and pass the actual id to the action that opens the form
                # also allows to place remarks in the chatter of the new record
                new_record = self.env[self._workflow_model].create(
                    new_record._convert_to_write(new_record._cache)
                )
                services = [new_record]
                action["res_id"] = new_record.id

            # Now create related records, such as chatter remarks, based on the actual ID of the root record
            for service in services:
                self.create_related_records(service)

        return action

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        transition_id = self.env.context.get("transition_id")
        defaultValues["transition_id"] = transition_id
        transition = self.env["riverflow.transition"].browse(transition_id)
        defaultValues["transition_description"] = transition.description

        isStartTransition = transition.from_state_id.id == False
        if isStartTransition:
            defaultValues["record_ids"] = [Command.set([])]
        else:
            record_ids = self.env.context.get("active_ids")
            if record_ids:
                services = self.env["riverflow.service"].browse(record_ids)
                defaultValues["record_ids"] = [Command.set(services.ids)]

                # if len(services) == 1:
                #     service = services[0]
                #     defaultValues["name"] = service.name
                #     defaultValues["new_remark"] = ""
                #     defaultValues["days_relative_to_project"] = service[
                #         "days_relative_to_project"
                #     ]

        return defaultValues

    # abstract methods
    def create_related_records(self, record):
        pass

    def set_property_values(self, record):
        pass
