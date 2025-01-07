from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError


class TransitionWizard(models.AbstractModel):
    _name = "riverflow.transition.wizard"
    _description = "Transition action base Wizard"

    _workflow_model = "definedInDerivedClass"

    transition_id = fields.Many2one("riverflow.transition", "Transition")
    transition_description = fields.Html(
        "Description", compute="_compute_transition_description"
    )
    transition_description_invisible = fields.Boolean()

    # in each derived class, define the records_to_transition_ids field to be of the correct co-model
    records_to_transition_ids = fields.Many2many(
        "riverflow.service"
    )  # to be overridden
    responsible_team_id = fields.Many2one(
        "riverflow.team",
        string="Assign to Team",
        help="Team responsible for the next step of the workflow",
    )
    responsible_team_id_invisible = fields.Boolean()
    new_note = fields.Text(string="Internal Note")
    new_note_invisible = fields.Boolean()

    @api.model
    def default_get(self, form_fields):
        defaultValues = super().default_get(form_fields)

        transition_id = self.env.context.get("transition_id")
        transition_id = self.env["riverflow.transition"].browse(transition_id)
        defaultValues["transition_id"] = transition_id.id

        if transition_id.to_responsible_team_id:
            defaultValues["responsible_team_id"] = (
                transition_id.to_responsible_team_id.id
            )

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

        visibility_defaults = self.get_visibility_defaults(transition_id)
        # Update defaultValues with new values, without overwriting existing ones, so that
        # the defaults given by the calling action are kept (e.g. from action_context)
        for key, value in visibility_defaults.items():
            if key not in defaultValues:
                defaultValues[key] = value

        return defaultValues

    def get_visibility_defaults(self, transition_id):
        return {
            "responsible_team_id_invisible": transition_id.to_state_id.is_end_state,
        }

    def action_save(self):
        for wizard in self:
            transition = wizard.transition_id

            if not transition:
                raise ValidationError("Workflow Transition not specified")

            recordsToTransition = wizard.records_to_transition_ids

            createNewRecord = len(recordsToTransition) == 0
            create_vals = {}
            if createNewRecord:
                create_vals["workflow_id"] = transition.workflow_id.id
                in_memory_record = self.env[self._workflow_model].new(create_vals)

                recordsToTransition = [in_memory_record]

                action = {
                    "type": "ir.actions.act_window",
                    "res_model": self._workflow_model,
                    "res_id": 0,  # NewId value, will be updated below
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
            expected_state = transition.from_state_id
            for record in recordsToTransition:
                current_state = record.state_id
                if expected_state and current_state != expected_state:
                    raise UserError(
                        _(
                            "Another user just updated this record. Please refresh and try again."
                        )
                    )

                write_vals = {"state_id": transition.to_state_id.id}
                self.update_write_values(record, write_vals)

                if not createNewRecord:
                    record.write(write_vals)
                    self.create_related_records(record)
                else:
                    # Merge write_vals into create_vals
                    create_vals.update(write_vals)

                    new_record = (
                        self.env[self._workflow_model]
                        .with_context(
                            mail_create_nosubscribe=True,  # current user not made followers of the record thread
                            mail_auto_subscribe_no_notify=True,  # recipients are not notified of the record thread
                        )
                        .create(create_vals)
                    )
                    action["res_id"] = new_record.id
                    self.create_related_records(new_record)

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
            description = ""
            if wizard.transition_id.description:
                description = wizard.transition_id.description

            wizard.transition_description = description

    def default_get_using_records(self, defaultValues, records_to_transition):
        pass

    def update_write_values(self, record, vals):
        if not self.responsible_team_id_invisible:
            vals["responsible_team_id"] = self.responsible_team_id.id

    def _is_to_end_state(self):
        return self.transition_id.to_state_id.is_end_state
