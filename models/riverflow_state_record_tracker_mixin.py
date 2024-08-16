from odoo import _, fields, models, api
from odoo.addons.riverflow.models.riverflow_transition_mixin import RiverflowTransitionMixin  # type: ignore

"""
This mixin maintains a global view of services and their parent entities through the RiverflowStateRecord model.

Key features:
- Automatic synchronization of the current model with a global state record 
  for efficient querying
"""


class RiverflowWorkflowStateRecordTrackerMixin(models.AbstractModel):
    _name = "riverflow.state.record.tracker.mixin"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._create_state_record(records)
        return records

    def write(self, vals):
        result = super().write(vals)
        self._update_state_record(vals)
        return result

    def unlink(self):
        self._unlink_state_record()
        return super().unlink()

    @api.model
    def _create_state_record(self, records):
        state_record_vals = []
        for record in records:
            state_record_vals.append(
                {
                    "name": record.display_name,
                    "model": record._name,
                    "res_id": record.id,
                    "workflow_id": record.workflow_id.id,
                    "state_id": record.state_id.id,
                    "from_transition_ids": [(6, 0, record.from_transition_ids.ids)],
                    "current_workflow_name": record.current_workflow_name,
                    "state_name": record.state_name,
                    "transition_buttons_json": record.transition_buttons_json,
                }
            )
        self.env["riverflow.state.record"].sudo().create(state_record_vals)

    def _update_state_record(self, vals):
        for record in self:
            state_record = (
                self.env["riverflow.state.record"]
                .sudo()
                .search(
                    [("model", "=", record._name), ("res_id", "=", record.id)], limit=1
                )
            )

            if state_record:
                update_vals = {}
                if "name" in vals:
                    update_vals["name"] = record.display_name
                if "workflow_id" in vals:
                    update_vals["workflow_id"] = record.workflow_id.id
                if "state_id" in vals:
                    update_vals["state_id"] = record.state_id.id
                if "from_transition_ids" in vals:
                    update_vals["from_transition_ids"] = [
                        (6, 0, record.from_transition_ids.ids)
                    ]
                if "current_workflow_name" in vals:
                    update_vals["current_workflow_name"] = record.current_workflow_name
                if "state_name" in vals:
                    update_vals["state_name"] = record.state_name
                if "transition_buttons_json" in vals:
                    update_vals["transition_buttons_json"] = (
                        record.transition_buttons_json
                    )

                if update_vals:
                    state_record.write(update_vals)

    def _unlink_state_record(self):
        self.env["riverflow.state.record"].sudo().search(
            [("model", "=", self._name), ("res_id", "in", self.ids)]
        ).unlink()
