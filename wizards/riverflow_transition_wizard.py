from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError


class TransitionWizard(models.AbstractModel):
    _name = "riverflow.transition.wizard"
    _description = "Transition action base Wizard"

    _workflow_model = "definedInDerivedClass"

    transition_id = fields.Many2one("riverflow.transition", "Transition")
    transition_description = fields.Text("Description")

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        transition_id = self.env.context.get("transition_id")
        defaultValues["transition_id"] = transition_id
        transition = self.env["riverflow.transition"].browse(transition_id)
        defaultValues["transition_description"] = transition.description

        isStartTransition = transition.from_state_id.id == False
        records_to_transition = self.env[self._workflow_model]
        records_to_transition_ids = []
        # if we are in a wizard that is triggered by a record,
        # as opposed to a start-transition selection wizard,
        # then use the active ids
        if self.env.context.get("active_model") == self._workflow_model:
            records_to_transition_ids = self.env.context.get("active_ids")
        if records_to_transition_ids:
            records_to_transition = records_to_transition.browse(
                records_to_transition_ids
            )

        if records_to_transition.ids:
            defaultValues["records_to_transition_ids"] = records_to_transition.ids

        self.default_get_using_records(defaultValues, records_to_transition)

        return defaultValues

    def action_save(self):
        for wizard in self:
            transition = wizard.transition_id

            if not transition:
                raise exceptions.ValidationError("Workflow Transition not specified")

            recordsToTransition = wizard.records_to_transition_ids

            createNewRecord = len(recordsToTransition) == 0
            if createNewRecord:
                new_record = self.env[self._workflow_model].new(
                    {
                        "workflow_id": transition.workflow_id.id,
                    }
                )

                recordsToTransition = [new_record]

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

            # Collect the property values that need to be updated and pass
            # them in one go write(), so that the validations @api.constrains
            # get triggered on a record with all the new property values
            for record in recordsToTransition:
                vals = {"state_id": transition.to_state_id.id}
                self.updated_property_values(record, vals)
                record.write(vals)

            if createNewRecord:
                # Save the record to the database, and pass the actual id to the action that opens the form
                # also allows to place remarks in the chatter of the new record
                new_record = (
                    self.env[self._workflow_model]
                    .with_context(
                        mail_create_nosubscribe=True,  # individual team members are not subscribed to the record thread
                        mail_auto_subscribe_no_notify=True,  # individual team members are not notified of the record thread
                    )
                    .create(new_record._convert_to_write(new_record._cache))
                )
                recordsToTransition = [new_record]
                action["res_id"] = new_record.id

            # Now create related records, such as chatter remarks, based on the actual ID of the root record
            for record in recordsToTransition:
                self.create_related_records(record)

        return action

    # abstract methods
    def create_related_records(self, record):
        pass

    def default_get_using_records(self, defaultValues, records_to_transition):
        pass

    def updated_property_values(self, record, vals):
        pass
