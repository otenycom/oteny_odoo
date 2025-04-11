# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import time

_logger = logging.getLogger(__name__)


class RiverflowImport(models.AbstractModel):
    """
    Abstract model that provides batch import functionality with external IDs.
    """

    _name = "riverflow.import"
    _description = "Riverflow Import Utilities"

    @api.model
    def batch_create_with_external_ids(self, model_name, records, update_if_exists=True):
        """
        Batch create or update records with external IDs for any model.

        Args:
            model_name (str): The technical name of the model to create records for
            records (list): List of dictionaries. Each dict must contain 'xml_id' key with
                           the external ID and the rest of the fields to create/update.
            update_if_exists (bool): If True, update existing records, otherwise skip them

        Returns:
            dict: Results of the operation with counts and details
        """
        if not records:
            return {
                "status": "error",
                "message": "No records provided",
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        Model = self.env[model_name]
        IrModel = self.env["ir.model.data"]

        result = {
            "status": "success",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
        }

        # --- Preparation Phase ---
        xml_ids = []
        valid_records_map = {}
        for i, record in enumerate(records):
            if "xml_id" not in record:
                result["errors"].append({"error": "Missing xml_id", "record_index": i, "record": record})
                continue

            xml_id = record["xml_id"]
            if "." not in xml_id:
                result["errors"].append(
                    {
                        "error": "Invalid xml_id format. Must contain module name: module.identifier",
                        "xml_id": xml_id,
                        "record_index": i,
                    }
                )
                continue
            xml_ids.append(xml_id)
            # Store original record and index for later processing
            valid_records_map[xml_id] = {"data": record, "index": i}

        if not xml_ids:
            result["status"] = "error"
            result["message"] = "No valid records with xml_id found"
            return result

        # Pre-fetch existing ir.model.data records
        existing_imds_map = {
            f"{imd.module}.{imd.name}": imd
            for imd in IrModel.search(
                [
                    ("module", "in", [xid.split(".", 1)[0] for xid in xml_ids]),
                    ("name", "in", [xid.split(".", 1)[1] for xid in xml_ids]),
                    ("model", "=", model_name),
                ]
            )
        }

        create_vals_list = []  # Data for Model.create()
        create_imd_prep = []  # Data for IrModel.create() preparation
        update_ops = []  # Tuples of (res_id, vals) for update
        skipped_xml_ids = []

        for xml_id in xml_ids:
            record_info = valid_records_map[xml_id]
            record_data = record_info["data"].copy()
            record_data.pop("xml_id")  # Remove xml_id from data payload
            module, name = xml_id.split(".", 1)

            existing_imd = existing_imds_map.get(xml_id)

            if existing_imd:
                if update_if_exists:
                    update_ops.append((existing_imd.res_id, record_data, xml_id))
                else:
                    skipped_xml_ids.append(xml_id)
                    result["skipped"] += 1
            else:
                create_vals_list.append(record_data)
                # Store necessary info to create ir.model.data later
                create_imd_prep.append(
                    {
                        "module": module,
                        "name": name,
                        "model": model_name,
                        "_xml_id": xml_id,  # Temporary key to link back
                    }
                )

        # --- Batch Creation Phase ---
        created_records = self.env[model_name]
        imd_create_vals = []
        if create_vals_list:
            try:
                # Use tracking_disable for potentially better performance on mass create
                created_records = Model.with_context(tracking_disable=True).create(create_vals_list)
                if len(created_records) != len(create_vals_list):
                    # This indicates a potential issue, maybe partial creation?
                    # Accurate error reporting becomes difficult here. Logging a general warning.
                    _logger.warning(
                        f"Batch create for {model_name}: Expected {len(create_vals_list)} records, created {len(created_records)}."
                    )
                    # We'll proceed assuming the created ones match the start of the list
                    # A more robust solution might need record-by-record creation upon error.

                # Prepare ir.model.data values, assuming order is preserved
                for i, new_record in enumerate(created_records):
                    if i < len(create_imd_prep):  # Check bounds in case of partial creation
                        imd_prep_data = create_imd_prep[i]
                        xml_id = imd_prep_data.pop("_xml_id")  # Retrieve and remove temp key
                        imd_prep_data["res_id"] = new_record.id
                        imd_create_vals.append(imd_prep_data)
                        result["created"] += 1
                        _logger.info(f"Prepared ir.model.data for created record {xml_id}")
                    else:
                        # This case should ideally not happen if len(created_records) == len(create_vals_list)
                        _logger.error(f"Mismatch in created records and prepared IMD data for {model_name}")

            except Exception as e:
                _logger.error(f"Error during batch create for model {model_name}: {e}", exc_info=True)
                result["errors"].append(
                    {
                        "error": f"Batch create failed: {e}",
                        "details": "",
                        # Cannot easily pinpoint which specific record failed in batch
                    }
                )
                # Clear lists to prevent attempting ir.model.data creation
                imd_create_vals = []
                result["created"] = 0  # Reset count as the main batch failed

        if imd_create_vals:
            try:
                IrModel.create(imd_create_vals)
                _logger.info(f"Batch created {len(imd_create_vals)} ir.model.data records for {model_name}")
            except Exception as e:
                _logger.error(f"Error during batch create for ir.model.data: {e}", exc_info=True)
                # Log which xml_ids might have failed based on the prepared data
                failed_xml_ids = [
                    d.get("name", "unknown") for d in imd_create_vals
                ]  # name corresponds to xml_id name part
                result["errors"].append(
                    {
                        "error": f"Batch ir.model.data create failed: {e}",
                        "details": f"Could not create external IDs. Associated xml_ids might include: {', '.join(failed_xml_ids)}",
                    }
                )
                # Note: The main records were already created in the previous step.
                # We don't decrement result["created"] here, but the status will reflect the error.

        # --- Update Phase ---
        if update_ops:
            # Fetch records to update efficiently
            ids_to_update = [op[0] for op in update_ops]
            try:
                records_to_update = Model.browse(ids_to_update).exists()  # Ensure they exist
                records_map = {rec.id: rec for rec in records_to_update}

                for res_id, vals, xml_id in update_ops:
                    record_to_update = records_map.get(res_id)
                    if record_to_update:
                        try:
                            record_to_update.write(vals)
                            result["updated"] += 1
                            _logger.info(f"Updated record with external ID {xml_id}")
                        except Exception as e:
                            _logger.error(
                                f"Error updating record {xml_id} (ID: {res_id}): {e}", exc_info=True
                            )
                            result["errors"].append({"error": str(e), "xml_id": xml_id, "data": vals})
                    else:
                        # This case means ir.model.data exists but the underlying record (res_id) doesn't
                        _logger.warning(
                            f"Record for xml_id {xml_id} (res_id: {res_id}) not found for update, despite existing ir.model.data."
                        )
                        result["errors"].append(
                            {"error": "Record not found for update", "xml_id": xml_id, "res_id": res_id}
                        )
            except Exception as e:
                _logger.error(f"Error fetching records for update (model {model_name}): {e}", exc_info=True)
                result["errors"].append(
                    {
                        "error": f"Failed to fetch records for update: {e}",
                        "details": "Updates could not be processed.",
                    }
                )

        # --- Finalization ---
        if skipped_xml_ids:
            _logger.info(f"Skipped {len(skipped_xml_ids)} existing records: {', '.join(skipped_xml_ids)}")

        if result["errors"]:
            for error in result["errors"]:
                # Log detailed errors if available
                _logger.error(
                    f"Error processing record: {error.get('xml_id', 'N/A')} - {error['error']} - Data: {error.get('data', 'N/A')}"
                )
            result["status"] = "partial" if (result["created"] > 0 or result["updated"] > 0) else "error"

        return result
