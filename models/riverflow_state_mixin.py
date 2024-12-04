from odoo import _, fields, models, api
from odoo.addons.riverflow.models.riverflow_transition_mixin import RiverflowTransitionMixin  # type: ignore
import json


class RiverflowWorkflowStateMixin(RiverflowTransitionMixin):
    _name = "riverflow.state.mixin"
    _description = "Mixin to support workflow state in any model"

    # initial workflow. Not a computed field, so it can be set in the form view
    # and the user can then select the state. If state is change later in write/create, we keep
    # the workflow_id as it was set initially, so it represents the front office workflow/work status
    workflow_id = fields.Many2one(
        "riverflow.workflow",
        domain="[('model', '=', model)]",
        string="Workflow",
        tracking=True,
        index=True,
    )

    state_id = fields.Many2one(
        "riverflow.state",
        "State",
        tracking=True,
        index=True,
        help="Current workflow state",
    )
    state_id_statusbar_json = fields.Json(
        "Statusbar Info", compute="_compute_state_id_statusbar_json", store=False
    )
    from_transition_ids = fields.Many2many(
        "riverflow.transition",
        compute="_compute_from_transition_ids",
    )

    current_workflow_name = fields.Char(
        "Workflow name",
        related="workflow_id.name",
        store=True,
        index=True,
    )
    state_name = fields.Char(
        "State name", related="state_id.name", store=True, index=True
    )

    state_json = fields.Json(
        string="State Info", compute="_compute_state_json", store=False
    )
    transition_buttons_json = fields.Json(
        string="Workflow Actions",
        compute="_compute_transition_buttons_json",
        store=False,
    )

    deadline = fields.Date(
        string="Deadline",
        compute="_compute_deadline",
        store=True,
        index=True,
        help="Planning deadline.",
    )

    timing_json = fields.Json(
        "Timing",
        compute="_compute_timing_json",
        store=False,
    )

    is_end_state = fields.Boolean(
        "Is End State",
        compute="_compute_is_end_state",
        store=True,
        index=True,
    )

    # = self._name, made accessible for use in the filter-domain of the workflow dropdown
    model = fields.Char(
        compute="_compute_model", help="Model on which the workflow runs."
    )

    @api.model
    def default_get(self, fields_list):
        res = super(RiverflowWorkflowStateMixin, self).default_get(fields_list)
        res["model"] = self._name
        return res

    @api.model
    def _compute_model(self):
        for record in self:
            record.model = record._name

    @api.onchange("workflow_id", "state_id")
    def on_change_workflow_id(self):
        for s in self:
            if s.workflow_id and not s.state_id:
                startStates = self.env["riverflow.state"].search(
                    [
                        ("workflow_id", "=", s.workflow_id.id),
                    ],
                    limit=1,
                    order="sequence,name,id",
                )
                if len(startStates):
                    s.state_id = startStates[0]

    @api.depends("state_id", "state_id.from_transition_ids")
    def _compute_from_transition_ids(self):
        for s in self:
            if not s.state_id:
                if s.workflow_id:
                    domain = [
                        ("from_state_id", "=", False),
                        ("workflow_id", "=", s.workflow_id.id),
                    ]
                    s.from_transition_ids = self.env["riverflow.transition"].search(
                        domain, order="workflow_name,sequence,id"
                    )
                else:
                    s.from_transition_ids = []
            else:
                s.from_transition_ids = self.env["riverflow.transition"].search(
                    [
                        ("from_state_id", "=", s.state_id.id),
                    ],
                    order="sequence,id",
                )

    def _compute_state_json(self):
        # for rendering just the state name and workflow name
        for record in self:
            wf_state_text = record.current_workflow_name or ""
            if wf_state_text or record.state_name:
                state_text = record.state_name or "Not Started"
                wf_state_text = " | ".join([wf_state_text, state_text])

            # todo: store the icon so its not a lookup
            icon = record.workflow_id.icon or ""
            is_end_state = record.is_end_state == True

            state_json = {
                "text": wf_state_text,
                "workflow_name": record.current_workflow_name,
                "workflow_icon": icon,
                "is_end_state": is_end_state,
                # this is not a start transition, so we can refresh the underlying list/form view
                "reload_on_close": True,
                "buttons": [],
            }

            record.state_json = state_json

    @api.depends("state_json")
    def _compute_transition_buttons_json(self):
        # for rendering the transition buttons below the state name
        for record in self:
            transition_buttons = record.state_json
            transition_ids = record.from_transition_ids
            if transition_ids:
                index = 0
                for transition in transition_ids:
                    # workaround, sometimes transition is a clone? in lookup tables or so
                    transition_id = (
                        transition.id.origin
                        if isinstance(record.id, models.NewId)
                        else int(transition.id)
                    )

                    transition_buttons["buttons"].append(
                        {
                            "index": index,
                            "caption": transition.name,
                            "help": transition.description,
                            "action": "action_button_click",
                            # context is posted back to the server side action method
                            "context": {
                                "transition_id": transition_id,
                            },
                        }
                    )
                    index += 1

            record.transition_buttons_json = transition_buttons

    def _compute_state_id_statusbar_json(self):
        for record in self:
            current_state_id = record.state_id
            if current_state_id:
                workflow_id = current_state_id.workflow_id.id
            else:
                workflow_id = record.workflow_id.id

            state_ids = self.env["riverflow.state"].search(
                [("workflow_id", "=", workflow_id)]
            )

            json = {"states": []}
            is_first = True

            for state in state_ids:
                if current_state_id:
                    is_current_state = state.id == current_state_id.id
                else:
                    is_current_state = is_first
                    is_first = False

                if not state.hide_in_statusbar or is_current_state:
                    json["states"].append(
                        {
                            "value": state.id,
                            "label": state.name,
                            "isFolded": state.hide_in_statusbar,
                            "isSelected": is_current_state,
                        }
                    )

            record.state_id_statusbar_json = json

    def action_button_click(self):

        return self._prepare_transition_action()

    def write(self, vals):
        self._sync_workflow_with_state(vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_workflow_with_state(vals)
        records = super().create(vals_list)
        # self.env["riverflow.auto.add.service"].auto_add_services(records)
        return records

    def _sync_workflow_with_state(self, vals):
        if "state_id" in vals:
            if vals["state_id"]:
                new_state = self.env["riverflow.state"].browse(vals["state_id"])
                vals["workflow_id"] = new_state.workflow_id.id
            else:
                vals["workflow_id"] = False

    def _compute_deadline(self):
        pass

    @api.depends("deadline", "is_end_state")
    def _compute_timing_json(self):
        Service = self.env["riverflow.service"]
        for record in self:
            if not record.deadline:
                record.timing_json = False
                continue

            date_str = record.deadline.strftime(Service.DATE_FORMAT)

            today = fields.Date.today()
            days_remaining = (record.deadline - today).days
            is_past = record.deadline < today
            is_today = record.deadline == today

            record.timing_json = {
                "relative_days": "",
                "date": date_str,
                "days_remaining": days_remaining,
                "is_past": is_past,
                "is_today": is_today,
                "is_end_state": record.is_end_state,
            }

    @api.depends("from_transition_ids", "state_id.is_end_state")
    def _compute_is_end_state(self):
        for record in self:
            if record.state_id:
                record.is_end_state = record.state_id.is_end_state
            else:
                # start transitions are not end states
                record.is_end_state = len(record.from_transition_ids) == 0
