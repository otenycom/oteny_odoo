from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError


class TransitionWizard(models.AbstractModel):
    _name = "riverflow.transition.wizard"
    _description = "Transition action base Wizard"

    _workflow_model = "definedInDerivedClass"

    transition_id = fields.Many2one("riverflow.transition", "Transition")
    transition_description = fields.Text(
        "Description", compute="_compute_transition_description"
    )

    # in each derived class, define the records_to_transition_ids field to be of the correct co-model
    records_to_transition_ids = fields.Many2many(
        "riverflow.service"
    )  # to be overridden
    responsible_team_id = fields.Many2one(
        "riverflow.team",
        string="Responsible Team",
        help="Team executing the workflow of this record.",
    )
    responsible_team_id_invisible = fields.Boolean(compute="_compute_field_visibility")
    new_note = fields.Text(string="Internal Note")
    new_note_invisible = fields.Boolean(compute="_compute_field_visibility")

    @api.depends("transition_id")
    def _compute_field_visibility(self):
        for wizard in self:
            wizard.responsible_team_id_invisible = self._is_to_end_state()
            wizard.new_note_invisible = False

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        transition_id = self.env.context.get("transition_id")
        defaultValues["transition_id"] = transition_id

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
        if not self.new_note_invisible and self.new_note:
            self.env["mail.message"].create(
                {
                    "body": self.new_note,
                    "model": self._workflow_model,
                    "res_id": record.id,
                    "message_type": "comment",
                    "subtype_id": self.env.ref("mail.mt_note").id,
                }
            )

    @api.depends("transition_id")
    def _compute_transition_description(self):
        for wizard in self:
            if wizard.transition_id.from_state_id:
                wizard.transition_description = (
                    wizard.transition_id.from_state_id.name
                    + " → "
                    + wizard.transition_id.to_state_id.name
                )
            else:  # start transition
                wizard.transition_description = wizard.transition_id.to_state_id.name
            if wizard.transition_id.description:
                wizard.transition_description += (
                    f" | {wizard.transition_id.description}"
                )

    def default_get_using_records(self, defaultValues, records_to_transition):
        pass

    def updated_property_values(self, record, vals):
        if not self.responsible_team_id_invisible:
            vals["responsible_team_id"] = self.responsible_team_id.id

    def _is_to_end_state(self):
        return self.transition_id.to_state_id.is_end_state
