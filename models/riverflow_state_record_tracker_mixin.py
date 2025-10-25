from odoo import _, fields, models, api
from odoo.addons.riverflow.models.riverflow_transition_mixin import RiverflowTransitionMixin  # type: ignore
import logging

_logger = logging.getLogger(__name__)

"""
This mixin maintains a global view of services and their parent entities through the RiverflowStateRecord model.

Key features:
- Automatic synchronization of the current model with a global state record 
  for efficient querying
"""


class RiverflowWorkflowStateRecordTrackerMixin(models.AbstractModel):
    _name = "riverflow.state.record.tracker.mixin"
    _description = "Syncs the model with the central Radar table (RiverflowStateRecord)."

    state_record_id = fields.Many2one(
        "riverflow.state.record",
        string="State Record",
        compute="_compute_state_record_id",
        store=True,
        readonly=True,
        ondelete="set null",
    )

    @api.depends("create_date")
    def _compute_state_record_id(self):
        if any(isinstance(record.id, api.NewId) for record in self):
            return

        needing_state_record = self.filtered(lambda r: not r.state_record_id)
        if not needing_state_record:
            return

        state_records = self._create_state_records(needing_state_record)
        for record in self:
            state_record = state_records.filtered(
                lambda r: r.master_res_id == record.id and r.master_model == record._name
            )
            record.state_record_id = state_record.id

    def _create_state_records(self, records):
        state_record_vals = []
        for record in records:
            if self._add_state_record(record):
                # _logger.info(f"Creating riverflow_state_record for {record._name} with id {record.id}")
                # The rest of the values are copied from the record by compute methods in the state record model
                vals = {
                    "master_model": record._name,
                    "master_res_id": record.id,
                }
                state_record_vals.append(vals)
        if len(state_record_vals) > 0:
            return self.env["riverflow.state.record"].create(state_record_vals)
        return self.env["riverflow.state.record"]

    @api.model
    def _add_state_record(self, record):
        return True

    def unlink(self):
        # we first unlink the master record, as during its unlink, it will flush writes to the state record
        # for computed values. These flushes fail if we remove the state record from under the feet of the master record
        # Filter out any records that don't exist (have been deleted) before trying to access their fields
        existing_records = self.filtered(lambda r: r.exists())
        state_records = existing_records.mapped("state_record_id")
        result = super().unlink()
        state_records.sudo().unlink()
        return result
