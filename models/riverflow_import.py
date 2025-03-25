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

        for record in records:
            if "xml_id" not in record:
                result["errors"].append({"error": "Missing xml_id", "record": record})
                continue

            xml_id = record.pop("xml_id")
            if "." not in xml_id:
                result["errors"].append(
                    {
                        "error": "Invalid xml_id format. Must contain module name: module.identifier",
                        "xml_id": xml_id,
                    }
                )
                continue

            module, name = xml_id.split(".", 1)

            try:
                # Check if the record already exists
                existing = IrModel.search(
                    [
                        ("module", "=", module),
                        ("name", "=", name),
                        ("model", "=", model_name),
                    ]
                )

                if existing:
                    existing_record = self.env.ref(xml_id, raise_if_not_found=False)
                    if not existing_record:
                        result["errors"].append(
                            {"error": "External ID exists but record not found", "xml_id": xml_id}
                        )
                        continue

                    if update_if_exists:
                        existing_record.write(record)
                        result["updated"] += 1
                        _logger.info(f"Updated record with external ID {xml_id}")
                    else:
                        result["skipped"] += 1
                        _logger.info(f"Skipped existing record with external ID {xml_id}")
                else:
                    # Create the record and external ID
                    new_record = Model.create(record)
                    IrModel.create(
                        {
                            "module": module,
                            "name": name,
                            "model": model_name,
                            "res_id": new_record.id,
                        }
                    )
                    result["created"] += 1
                    _logger.info(f"Created record with external ID {xml_id}")

            except Exception as e:
                result["errors"].append({"error": str(e), "xml_id": xml_id, "data": record})
                _logger.error(f"Error processing record with xml_id {xml_id}: {str(e)}")

        if result["errors"]:
            for error in result["errors"]:
                _logger.error(f"Error processing record with xml_id {error['xml_id']}: {error['error']}")
            result["status"] = "partial" if (result["created"] > 0 or result["updated"] > 0) else "error"

        return result
