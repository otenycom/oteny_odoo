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
    _description = "This mixin maintains a global view of services and their parent entities through the RiverflowStateRecord model."

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
        return (
            self.env["riverflow.state.record"]
            .sudo()
            .with_context(active_test=False)
            .search(domain)
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._create_state_record(records)
        return records

    # overriding _write not write, so we also see the computed field values
    def _write(self, vals):
        result = super()._write(vals)
        self._update_state_record(vals)
        return result

    def _unlink_state_record(self):
        state_records = self._get_state_records(ids=self.ids)
        if state_records:
            # Ensure we're only unlinking existing records
            existing_records = state_records.exists()
            if existing_records:
                _logger.info(
                    f"Unlinking {len(existing_records)} state records for {self._name} with ids {existing_records.ids}"
                )
                existing_records.sudo().unlink()
            else:
                _logger.warning(
                    f"Attempted to unlink non-existent state records for {self._name} with ids {self.ids}"
                )

    def unlink(self):
        _logger.info(f"Unlinking records of {self._name} with ids {self.ids}")
        # we first unlink the master record, as during its unlink, it will flush writes to the state record
        # for computed values. These flushes fail if we remove the state record from under the feet of the master record
        result = super().unlink()
        self._unlink_state_record()
        return result

    @api.model
    def _create_state_record(self, records):
        state_record_vals = []
        for record in records:
            _logger.info(
                f"Creating riverflow_state_record for {record._name} with id {record.id}"
            )
            vals = {
                "name": record.name,
                "display_name": record.display_name,
                "master_model": record._name,
                "master_res_id": record.id,
                "workflow_id": record.workflow_id.id,
                "state_id": record.state_id.id,
                "active": record.active if hasattr(record, "active") else True,
                "deadline": record.deadline if hasattr(record, "deadline") else False,
                "root_id": (record.root_id if hasattr(record, "root_id") else False),
                "root_name": (
                    record.root_name if hasattr(record, "root_name") else False
                ),
                "indented_name": (
                    record.indented_name
                    if hasattr(record, "indented_name")
                    else record.name
                ),
                "sequence": record.sequence if hasattr(record, "sequence") else 0,
                "tag_ids": (
                    [(6, 0, record.tag_ids.ids)]
                    if hasattr(record, "tag_ids")
                    else False
                ),
                "res_id": record.res_id if hasattr(record, "res_id") else record.id,
                "res_model": (
                    record.res_model if hasattr(record, "res_model") else record._name
                ),
                "res_name": (
                    record.res_name if hasattr(record, "res_name") else record.name
                ),
                # New fields from MailThreadReviewMixin
                "internal_notes_summary": (
                    record.internal_notes_summary
                    if hasattr(record, "internal_notes_summary")
                    else False
                ),
                "external_messages_summary": (
                    record.external_messages_summary
                    if hasattr(record, "external_messages_summary")
                    else False
                ),
                "unreviewed_message_count": (
                    record.unreviewed_message_count
                    if hasattr(record, "unreviewed_message_count")
                    else 0
                ),
                "responsible_team_id": (
                    record.responsible_team_id.id
                    if hasattr(record, "responsible_team_id")
                    else False
                ),
            }
            state_record_vals.append(vals)
        self.env["riverflow.state.record"].create(state_record_vals)

    def _update_state_record(self, vals):
        # if self.isInUnlink:
        #     return

        for record in self:
            state_record = record._get_state_record()

            if state_record:
                update_vals = {}
                fields_to_update = [
                    # fields from riverflow.state.mixin
                    "name",
                    "display_name",
                    "workflow_id",
                    "state_id",
                    # fields from riverflow.service
                    "active",
                    "deadline",
                    "root_name",
                    "root_id",
                    "sequence",
                    "tag_ids",
                    "res_id",
                    "res_model",
                    "res_name",
                    # fields from MailThreadReviewMixin
                    "internal_notes_summary",
                    "external_messages_summary",
                    "unreviewed_message_count",
                    "responsible_team_id",
                ]

                for field in fields_to_update:
                    if field in vals:
                        if field == "tag_ids":
                            update_vals[field] = [(6, 0, record.tag_ids.ids)]
                        else:
                            update_vals[field] = vals[field]

                master_model_fields = self.env[self._name]._fields
                if "res_name" not in master_model_fields:
                    if "name" in vals:
                        # for sorting master records just before its services, we use the
                        # res_name field and the sequence field
                        update_vals["res_name"] = vals["name"]

                if update_vals:
                    state_record.sudo().write(update_vals)
