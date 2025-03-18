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

    def _get_state_record(self):
        self.ensure_one()
        state_record = self._get_state_records(ids=[self.id])
        return state_record

    def _get_state_records(self, ids):
        """
        Retrieve state records for the current model, including archived ones.

        :param ids: Optional list of record IDs to filter by
        :return: Recordset of riverflow.state.record
        """
        domain = [("master_model", "=", self._name)]
        domain.append(("master_res_id", "in", ids))
        return self.env["riverflow.state.record"].sudo().with_context(active_test=False).search(domain)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._create_state_record(records)
        return records

    def _unlink_state_record(self):
        state_records = self._get_state_records(ids=self.ids)
        if state_records:
            existing_records = state_records.exists()
            if existing_records:
                existing_records.sudo().unlink()

    def unlink(self):
        # we first unlink the master record, as during its unlink, it will flush writes to the state record
        # for computed values. These flushes fail if we remove the state record from under the feet of the master record
        result = super().unlink()
        self._unlink_state_record()
        return result

    @api.model
    def _create_state_record(self, records):
        state_record_vals = []
        for record in records:
            if self._add_state_record(record):
                _logger.info(f"Creating riverflow_state_record for {record._name} with id {record.id}")
                # The rest of the values are copied from the record by compute methods in the state record model
                vals = {
                    "master_model": record._name,
                    "master_res_id": record.id,
                }
                state_record_vals.append(vals)
        if len(state_record_vals) > 0:
            self.env["riverflow.state.record"].create(state_record_vals)

    @api.model
    def _add_state_record(self, record):
        return True
