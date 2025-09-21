# audit_log/models/base_patch.py
from collections import defaultdict
from odoo import models, api
from odoo.tools import SQL

original_create = models.BaseModel.create
original_unlink = models.BaseModel.unlink
original_write = models.BaseModel.write
original_flush = models.BaseModel._flush


def _create_audit_log_references(env, model, log_records):
    """
    Create reference entries for all audit logs.
    Creates both direct references (log points to itself) and parent references (child logs point to parents).

    Args:
        env: The Odoo environment.
        model: The model class being audited.
        log_records: A recordset of `oteny.audit.log`.
    """
    if not log_records:
        return

    refs = []

    # First, create direct references for ALL logs (each log points to itself)
    for log in log_records:
        refs.append(
            {
                "audit_log_id": log.id,
                "target_model_name": log.model_name,
                "target_record_id": log.record_id,
                "target_display_name": log.record_display_name,
                "parent_display_name": False,  # For direct refs, no parent
                "is_direct": True,
                "create_date": log.create_date,
                "transaction_id": log.transaction_id,
            }
        )

    # Now create parent references (for child logs that have parent relationships)
    # Group log records by their source record id to minimize queries
    logs_by_record_id = defaultdict(list)
    for log in log_records:
        logs_by_record_id[log.record_id].append(log)

    if logs_by_record_id:
        # Browse all source records at once
        records_with_logs = env[model._name].sudo().browse(list(logs_by_record_id.keys()))

        for record in records_with_logs:
            # Check if the record still exists before trying to access its fields
            if not record.exists():
                continue

            try:
                # Use unified parent resolution with recursion support
                # The function will determine the appropriate config for each record individually
                # and return all parent references found through recursion (ordered: immediate -> top-most)
                all_parent_refs = _resolve_parent_reference_unified(env, record, max_depth=3)

                # Create parent reference records for each level of recursion
                # List order: [immediate_parent, grandparent, great-grandparent, ...]
                if all_parent_refs:
                    for parent_ref_data in all_parent_refs:
                        parent_model_name = parent_ref_data["parent_model_name"]
                        parent_record_id = parent_ref_data["parent_record_id"]
                        parent_display_name = parent_ref_data["parent_display_name"]

                        # Create parent reference for each audit log of this record
                        for log in logs_by_record_id[record.id]:
                            refs.append(
                                {
                                    "audit_log_id": log.id,
                                    "target_model_name": parent_model_name,
                                    "target_record_id": parent_record_id,
                                    "target_display_name": log.record_display_name,  # Use child's display name for child logs
                                    "parent_display_name": parent_display_name,  # Store parent display name separately
                                    "is_direct": False,
                                    "create_date": log.create_date,
                                    "transaction_id": log.transaction_id,
                                }
                            )
            except Exception:
                # Failsafe for cases where parent record might be deleted or access rights issues.
                continue

    # Bulk create all references
    if refs:
        env["oteny.audit.log.ref"].sudo().create(refs)


def _resolve_parent_reference_unified(env, record, max_depth=3, current_depth=0):
    """
    Unified function to recursively resolve parent references up to max_depth levels.
    Handles both single field references and tuple formats for both _oteny_audit_parent_field and _model_parent_keys.

    Determines the appropriate parent configuration for each record individually:
    1. First checks for model-specific _oteny_audit_parent_field
    2. Falls back to predefined _model_parent_keys if no model-specific field exists

    Args:
        env: The Odoo environment.
        record: The record to find parent for.
        max_depth: Maximum recursion depth (default 3).
        current_depth: Current recursion depth.

    Returns:
        list: List of parent reference data dictionaries, each containing:
            - parent_model_name: The model name of the parent record
            - parent_record_id: The ID of the parent record
            - parent_display_name: The display name of the parent record
    """
    parent_refs = []

    if current_depth >= max_depth:
        return []

    # Determine parent configuration for this specific record
    parent_config = None

    # Check for model-specific _oteny_audit_parent_field first (takes precedence)
    model_parent_field = getattr(record.__class__, "_oteny_audit_parent_field", None)
    if model_parent_field:
        parent_config = model_parent_field
    else:
        # Fall back to predefined parent keys
        parent_keys = getattr(env["oteny.audit.log"], "_model_parent_keys", {})
        model_parent_key = parent_keys.get(record._name)
        if model_parent_key:
            parent_config = model_parent_key

    if not parent_config:
        return parent_refs

    try:
        # Parse the parent configuration - handle both single field and tuple formats
        if "," in parent_config:
            # Tuple format: "model,res_id" or similar
            config_fields = [field.strip() for field in parent_config.split(",")]
            if len(config_fields) == 2:
                model_field, id_field = config_fields
                if model_field in record._fields and id_field in record._fields:
                    parent_model_name = record[model_field]
                    parent_record_id = record[id_field]

                    if parent_model_name and parent_record_id and parent_model_name in env:
                        parent_record = env[parent_model_name].sudo().browse(parent_record_id).exists()
        else:
            # Single field format: "parent_id"
            parent_field = parent_config
            if parent_field in record._fields:
                parent_record = record[parent_field]
                if parent_record:
                    parent_model_name = parent_record._name
                    parent_record_id = parent_record.id

        # If we found a parent, add it to our parent references list
        if parent_record:
            parent_display_name = (
                parent_record.display_name
                if hasattr(parent_record, "display_name")
                else f"ID: {parent_record.id}"
            )

            parent_refs.append(
                {
                    "parent_model_name": parent_model_name,
                    "parent_record_id": parent_record_id,
                    "parent_display_name": parent_display_name,
                }
            )

            # If we haven't reached max depth, recursively resolve the parent's parent
            if current_depth < max_depth - 1:
                # Recursively resolve the parent's parent (grandparent, great-grandparent, etc.)
                # The function will determine the appropriate config for the parent record
                child_parent_refs = _resolve_parent_reference_unified(
                    env, parent_record, max_depth, current_depth + 1
                )
                # Add all parent references from the recursive call
                parent_refs.extend(child_parent_refs)

        return parent_refs

    except Exception:
        # Failsafe for cases where parent record might be deleted or access rights issues.
        return parent_refs


def _create_audit_logs(env, model, logs):
    """Helper to create audit log records and their references."""
    if not logs or not env.registry.loaded:
        return

    env.cr.execute("SELECT txid_current()")
    txid = env.cr.fetchone()[0]
    for log in logs:
        log["transaction_id"] = txid

    log_records = env["oteny.audit.log"].sudo().create(logs)
    _create_audit_log_references(env, model, log_records)


def _safe_convert_to_cache(field, raw_value, record):
    """
    Safely convert a raw value to cache format with fallback handling.

    This function handles edge cases where database values may be in unexpected formats,
    such as serialized dictionary strings or corrupted data.

    Args:
        field: The Odoo field object
        raw_value: The raw value from database or input
        record: The record instance for context

    Returns:
        The converted value in cache format, or string representation as fallback
    """
    if raw_value is None:
        return None

    try:
        # Handle special cases for raw values
        if isinstance(raw_value, dict):
            # Convert dict to string for storage/logging purposes
            value_for_cache = str(raw_value)
        else:
            value_for_cache = raw_value

        # Attempt the conversion
        return field.convert_to_cache(value_for_cache, record)

    except (ValueError, TypeError) as e:
        # Fallback: if conversion fails, use the raw value as string
        # This handles cases where database contains unexpected data formats
        return str(raw_value)


def _get_display_value(field, value, record_env):
    """Helper to get the display value for a field's value."""
    if value is None or value is False:
        return ""
    try:
        if field.type == "many2one" and isinstance(value, int):
            return record_env[field.comodel_name].sudo().browse(value).display_name
        if field.type in ["one2many", "many2many"] and isinstance(value, (list, tuple)):
            records = record_env[field.comodel_name].sudo().browse(list(value))
            return ", ".join(records.mapped("display_name"))
        if field.type == "selection":
            selection_values = dict(field.get_values(record_env))
            return selection_values.get(value, str(value))
    except Exception:
        # Fallback to string representation in case of errors (e.g., deleted records)
        # Limit string representation to 1000 characters to prevent excessive storage
        str_value = str(value)
        return str_value[:1000] + "..." if len(str_value) > 1000 else str_value
    return str(value)


@api.model_create_multi
def patched_create(self, vals_list):
    # Bypass if model is not yet fully loaded, or for the audit log model itself
    if not self.env.registry.loaded or self.env["oteny.audit.log"]._is_audit_ignored(self._name):
        return original_create(self, vals_list)

    records = original_create(self, vals_list)

    # Track newly created records in transaction scope
    # Also track which fields have been initially logged for each record
    audit_data = self.env.cr.precommit.data.setdefault("oteny_audit", {})
    if "newly_created_records" not in audit_data:
        audit_data["newly_created_records"] = defaultdict(set)
    if "initially_logged_fields" not in audit_data:
        audit_data["initially_logged_fields"] = defaultdict(lambda: defaultdict(set))
    newly_created = audit_data["newly_created_records"]
    newly_created[self._name].update(records.ids)

    # Skip if no records were created
    if not records:
        return records

    # Get all stored columns that are not readonly
    columns = [
        name
        for name, field in self._fields.items()
        if field.store and field.column_type and not field.readonly
    ]

    if columns:
        query = SQL(
            "SELECT id, %s FROM %s WHERE id IN %s",
            SQL(", ").join(SQL.identifier(col) for col in columns),
            SQL.identifier(self._table),
            tuple(records.ids),
        )
        self.env.cr.execute(query)
        new_data = self.env.cr.dictfetchall()
        new_values = {row["id"]: {col: row[col] for col in columns} for row in new_data}

        logs = []
        model_fields = self._fields
        for record in records:
            if hasattr(record, "display_name"):
                record_display_name = record.display_name
            else:
                record_display_name = f"ID: {record.id}"

            record_logs = []
            for col in columns:
                field = model_fields[col]
                raw_val = new_values.get(record.id, {}).get(col)
                new_val_cached = _safe_convert_to_cache(field, raw_val, record)

                if new_val_cached is None:
                    continue

                if field.default:
                    default_value = field.default(record)
                    default_value_cached = field.convert_to_cache(default_value, record)
                    if new_val_cached == default_value_cached:
                        continue
                elif new_val_cached == "":
                    continue

                new_val_display = _get_display_value(field, new_val_cached, record.env)

                record_logs.append(
                    {
                        "model_name": self._name,
                        "record_id": record.id,
                        "record_display_name": record_display_name,
                        "field_name": col,
                        "field_display_name": field.string,
                        "old_value": "",
                        "new_value": str(new_val_cached) if new_val_cached is not None else "",
                        "old_value_display_name": "",
                        "new_value_display_name": new_val_display,
                        "change_type": "i",
                    }
                )

            # If no logs were created for this record (all fields filtered out),
            # create a placeholder log entry to ensure the create operation is recorded
            if not record_logs:
                # Use 'id' field as placeholder if available, otherwise use first available field
                placeholder_field_name = "id" if "id" in model_fields else columns[0] if columns else None
                if placeholder_field_name:
                    field = model_fields[placeholder_field_name]
                    raw_val = new_values.get(record.id, {}).get(placeholder_field_name)
                    new_val_cached = _safe_convert_to_cache(field, raw_val, record)
                    new_val_display = _get_display_value(field, new_val_cached, record.env)

                    record_logs.append(
                        {
                            "model_name": self._name,
                            "record_id": record.id,
                            "record_display_name": record_display_name,
                            "field_name": placeholder_field_name,
                            "field_display_name": f"{field.string} (placeholder)",
                            "old_value": "",
                            "new_value": str(new_val_cached) if new_val_cached is not None else "",
                            "old_value_display_name": "",
                            "new_value_display_name": new_val_display,
                            "change_type": "i",
                        }
                    )

            logs.extend(record_logs)
        if logs:
            _create_audit_logs(self.env, self, logs)

            # Mark these fields as initially logged for newly created records
            initially_logged = audit_data["initially_logged_fields"]
            for log in logs:
                if log["record_id"] in newly_created[self._name]:
                    initially_logged[self._name][log["record_id"]].add(log["field_name"])

    return records


def patched_unlink(self):
    # Bypass if model is not yet fully loaded, or for the audit log model itself
    if not self.env.registry.loaded or self.env["oteny.audit.log"]._is_audit_ignored(self._name):
        return original_unlink(self)

    # Skip if no records are being unlinked
    if not self:
        return True

    columns = [
        name
        for name, field in self._fields.items()
        if field.store and field.column_type and not field.readonly
    ]

    old_values = {}
    if columns:
        query = SQL(
            "SELECT id, %s FROM %s WHERE id IN %s",
            SQL(", ").join(SQL.identifier(col) for col in columns),
            SQL.identifier(self._table),
            tuple(self.ids),
        )
        self.env.cr.execute(query)
        old_data = self.env.cr.dictfetchall()
        old_values = {row["id"]: {col: row[col] for col in columns} for row in old_data}

    logs = []
    model_fields = self._fields
    for record in self:
        try:
            record_display_name = record.display_name
        except Exception:
            record_display_name = f"ID: {record.id}"

        record_logs = []
        for col in columns:
            field = model_fields[col]
            raw_val = old_values.get(record.id, {}).get(col)
            old_val = _safe_convert_to_cache(field, raw_val, record)

            if old_val is None or old_val == "":
                continue

            old_val_display = _get_display_value(field, old_val, record.env)
            record_logs.append(
                {
                    "model_name": self._name,
                    "record_id": record.id,
                    "record_display_name": record_display_name,
                    "field_name": col,
                    "field_display_name": field.string,
                    "old_value": str(old_val) if old_val is not None else "",
                    "new_value": "",
                    "old_value_display_name": old_val_display,
                    "new_value_display_name": "",
                    "change_type": "d",
                }
            )

        # If no logs were created for this record (all fields filtered out),
        # create a placeholder log entry to ensure the delete operation is recorded
        if not record_logs:
            # Use 'id' field as placeholder if available, otherwise use first available field
            placeholder_field_name = "id" if "id" in model_fields else columns[0] if columns else None
            if placeholder_field_name:
                field = model_fields[placeholder_field_name]
                raw_val = old_values.get(record.id, {}).get(placeholder_field_name)
                old_val = _safe_convert_to_cache(field, raw_val, record)
                old_val_display = _get_display_value(field, old_val, record.env)

                record_logs.append(
                    {
                        "model_name": self._name,
                        "record_id": record.id,
                        "record_display_name": record_display_name,
                        "field_name": placeholder_field_name,
                        "field_display_name": f"{field.string} (placeholder)",
                        "old_value": str(old_val) if old_val is not None else "",
                        "new_value": "",
                        "old_value_display_name": old_val_display,
                        "new_value_display_name": "",
                        "change_type": "d",
                    }
                )

        logs.extend(record_logs)
    if logs:
        _create_audit_logs(self.env, self, logs)

    return original_unlink(self)


def patched_write(self, vals):
    # Bypass if model is not yet fully loaded, or for the audit log model itself
    if not self.env.registry.loaded or self.env["oteny.audit.log"]._is_audit_ignored(self._name):
        return original_write(self, vals)

    # Skip if no records or values are provided
    if not self or not vals:
        return original_write(self, vals)

    # Get all storable, non-readonly fields from vals
    fields_to_check = {
        name: self._fields[name]
        for name in vals
        if name in self._fields and self._fields[name].store and not self._fields[name].readonly
    }

    relational_fields = {n: f for n, f in fields_to_check.items() if f.type in ("one2many", "many2many")}
    scalar_fields = {n: f for n, f in fields_to_check.items() if f.type not in ("one2many", "many2many")}

    # --- IMMEDIATE LOGGING FOR RELATIONAL FIELDS ---
    # Relational field writes (like m2m with commands) are executed immediately.
    # We must capture the state before and after the original_write call.
    if relational_fields:
        # Pre-fetch old values for all records and all relational fields at once
        old_values_list = self.read(list(relational_fields.keys()))
        old_values_map = {rec["id"]: rec for rec in old_values_list}

    # --- DEFERRED LOGGING SETUP FOR SCALAR FIELDS ---
    # Scalar fields are not written until flush, so we just capture the old value
    # and let patched_flush handle the logging.
    if scalar_fields:
        # Use transaction-scoped storage instead of cursor attributes
        audit_data = self.env.cr.precommit.data.setdefault("oteny_audit", {})
        if "old_values" not in audit_data:
            audit_data["old_values"] = defaultdict(dict)

        # If a field is written to again, it should be logged again.
        # We remove it from the logged_changes cache to allow the next flush to process it.
        if "logged_changes" in audit_data:
            logged_changes = audit_data["logged_changes"]
            for field in scalar_fields.values():
                if field in logged_changes:
                    # Remove the records being written from the set of logged changes for this field.
                    logged_changes[field] -= set(self.ids)

        dirty_fields = self.env._field_dirty
        # Pre-fetch scalar fields not in cache to get their old values
        records_to_read_ids = {
            rec.id
            for rec in self
            for field in scalar_fields.values()
            if rec.id is not None
            and rec.id not in dirty_fields.get(field, set())
            and not self.env.cache.contains(rec, field)
        }
        if records_to_read_ids:
            self.sudo().browse(list(records_to_read_ids)).read(list(scalar_fields.keys()))

        for record in self:
            for name, field in scalar_fields.items():
                # Check if this field is already dirty for this record
                if record.id not in dirty_fields.get(field, set()):
                    # First modification: capture old value from cache if present
                    if self.env.cache.contains(record, field):
                        old_val = self.env.cache.get(record, field)
                        audit_data["old_values"][field][record.id] = old_val

    # Perform the original write for ALL fields
    result = original_write(self, vals)

    # --- FINISH IMMEDIATE LOGGING FOR RELATIONAL FIELDS ---
    if relational_fields:
        # Invalidate cache to ensure we re-read from the database
        self.invalidate_recordset(fnames=list(relational_fields.keys()))
        new_values_list = self.read(list(relational_fields.keys()))
        new_values_map = {rec["id"]: rec for rec in new_values_list}

        logs = []
        for record in self:
            old_rec_vals = old_values_map.get(record.id, {})
            new_rec_vals = new_values_map.get(record.id, {})
            try:
                record_display_name = record.display_name
            except Exception:
                record_display_name = f"ID: {record.id}"

            for name, field in relational_fields.items():
                old_ids = old_rec_vals.get(name, [])
                new_ids = new_rec_vals.get(name, [])

                # Odoo's read() returns a list of IDs for m2m.
                # To compare, we can just compare the sets of IDs.
                if set(old_ids) != set(new_ids):
                    # To get display values, we need to browse.
                    old_records = self.env[field.comodel_name].sudo().browse(old_ids)
                    new_records = self.env[field.comodel_name].sudo().browse(new_ids)

                    old_val_cache = field.convert_to_cache(old_records, record)
                    new_val_cache = field.convert_to_cache(new_records, record)

                    old_val_display = _get_display_value(field, old_val_cache, record.env)
                    new_val_display = _get_display_value(field, new_val_cache, record.env)

                    logs.append(
                        {
                            "model_name": self._name,
                            "record_id": record.id,
                            "record_display_name": record_display_name,
                            "field_name": name,
                            "field_display_name": field.string,
                            "old_value": str(old_val_cache) if old_val_cache is not None else "",
                            "new_value": str(new_val_cache) if new_val_cache is not None else "",
                            "old_value_display_name": old_val_display,
                            "new_value_display_name": new_val_display,
                            "change_type": "u",
                        }
                    )
        if logs:
            _create_audit_logs(self.env, self, logs)

    return result


def patched_flush(self, fnames=None):
    """
    Patched flush method that captures changes and logs them to audit table.
    Compatible with Odoo 18's flush signature.
    """
    # Bypass if model is not yet fully loaded, or for the audit log model itself
    if not self.env.registry.loaded or self.env["oteny.audit.log"]._is_audit_ignored(self._name):
        return original_flush(self)

    # Use transaction-scoped storage to prevent duplicate logging within the same transaction.
    audit_data = self.env.cr.precommit.data.setdefault("oteny_audit", {})
    if "logged_changes" not in audit_data:
        audit_data["logged_changes"] = defaultdict(set)
    logged_changes = audit_data["logged_changes"]

    records = self

    # Get dirty fields from cache
    dirty_fields_dict = self.env._field_dirty

    # Determine all fields of the current model that are dirty, regardless of `fnames`.
    # The original_flush will clear all of them from the cache, so we must audit all of them.
    all_dirty_model_fields = {
        field
        for field, dirty_ids in dirty_fields_dict.items()
        if field.model_name == self._name and dirty_ids
    }

    if not all_dirty_model_fields:
        # No dirty fields for this model to worry about.
        return original_flush(self)

    # Filter for fields that we can and should log (not readonly).
    loggable_fields_dict = {field.name: field for field in all_dirty_model_fields if not field.readonly}

    if not loggable_fields_dict:
        return original_flush(self)

    # Collect all dirty record IDs for the fields we're flushing, skipping already logged ones.
    all_ids = set()
    batches = {}

    for name, field in loggable_fields_dict.items():
        dirty_ids = dirty_fields_dict.get(field, set())
        # If specific records are passed, only flush those that are dirty
        if records._ids:
            batch_ids = dirty_ids & set(records._ids)
        else:
            # If `self` is an empty recordset, it implies we should flush for all dirty records of the model.
            batch_ids = dirty_ids

        # Filter out changes that have already been logged in this transaction
        unlogged_ids = batch_ids - logged_changes[field]

        if unlogged_ids:
            batches[name] = unlogged_ids
            all_ids.update(unlogged_ids)

    if not all_ids:
        # All dirty fields have already been logged in this transaction.
        return original_flush(self)

    # Get display names for all affected records
    display_names = {}
    for rec in self.sudo().browse(all_ids):
        try:
            display_names[rec.id] = rec.display_name
        except Exception:
            display_names[rec.id] = f"ID: {rec.id}"

    # Collect old values
    old_values = {}
    missing_queries = defaultdict(list)  # field: [ids needing DB query]
    audit_old_values = audit_data.get("old_values", {})
    # Track all record IDs that need to be checked for existence
    all_record_ids_to_check = set()

    for name, field in loggable_fields_dict.items():
        field_old_values = audit_old_values.get(field, {})
        for rid in batches.get(name, []):
            all_record_ids_to_check.add(rid)
            if rid in field_old_values:
                old_values.setdefault(rid, {})[name] = field_old_values[rid]
            else:
                missing_queries[field].append(rid)

    # Check which records are newly created in this transaction
    newly_created = audit_data.get("newly_created_records", {}).get(self._name, set())
    initially_logged = audit_data.get("initially_logged_fields", {}).get(self._name, {})

    # Query database for missing old values in a single batch
    if missing_queries:
        all_missing_ids = list({rid for rids in missing_queries.values() for rid in rids})
        all_missing_fields = list(missing_queries.keys())
        if all_missing_ids:
            field_names = [field.name for field in all_missing_fields if field.column_type]
            if field_names:
                query = SQL(
                    "SELECT id, %s FROM %s WHERE id IN %s",
                    SQL(", ").join(SQL.identifier(col) for col in field_names),
                    SQL.identifier(self._table),
                    tuple(all_missing_ids),
                )
                self.env.cr.execute(query)
                db_data_map = {row["id"]: row for row in self.env.cr.dictfetchall()}

                for field in all_missing_fields:
                    if field.name not in field_names:
                        continue
                    for rid in missing_queries[field]:
                        row = db_data_map.get(rid)
                        if row:
                            record = self.sudo().browse(rid)
                            val = _safe_convert_to_cache(field, row[field.name], record)
                            old_values.setdefault(rid, {})[field.name] = val
                        elif rid in newly_created:
                            # For new records, set old value as None/empty
                            old_values.setdefault(rid, {})[field.name] = None

    # Perform original flush
    original_flush(self)

    # After flush, re-read all flushed fields to get their new values
    # Use oteny_audit_ignore context to prevent infinite recursion
    if all_ids:
        new_values_list = (
            self.sudo()
            .browse(list(all_ids))
            .with_context(oteny_audit_ignore=True)
            .read(list(loggable_fields_dict.keys()))
        )
        new_values_map = {rec["id"]: rec for rec in new_values_list}
    else:
        new_values_map = {}

    # Log changes using old and new values
    logs = []
    if "most_recent_logs" not in audit_data:
        audit_data["most_recent_logs"] = defaultdict(lambda: defaultdict(dict))
    most_recent_logs = audit_data["most_recent_logs"]

    for name, field in loggable_fields_dict.items():
        for rid in batches.get(name, []):
            record = self.sudo().browse(rid)
            old_val = old_values.get(rid, {}).get(name)

            new_val_raw = new_values_map.get(rid, {}).get(name)
            new_val = _safe_convert_to_cache(field, new_val_raw, record)

            if old_val != new_val:
                most_recent = most_recent_logs[field].get(rid)
                if (
                    most_recent
                    and most_recent.get("old_value") == old_val
                    and most_recent.get("new_value") == new_val
                ):
                    continue

                # Determine change type: 'i' for new record fields not yet logged, 'u' otherwise
                # A field should be logged as 'i' if:
                # 1. The record was created in this transaction AND
                # 2. This specific field hasn't been initially logged yet
                is_new_field = rid in newly_created and name not in initially_logged.get(rid, set())
                change_type = "i" if is_new_field else "u"

                old_val_display = _get_display_value(field, old_val, record.env)
                new_val_display = _get_display_value(field, new_val, record.env)
                logs.append(
                    {
                        "model_name": self._name,
                        "record_id": rid,
                        "record_display_name": display_names.get(rid, f"ID: {rid}"),
                        "field_name": name,
                        "field_display_name": field.string,
                        "old_value": str(old_val) if old_val is not None else "",
                        "new_value": str(new_val) if new_val is not None else "",
                        "old_value_display_name": old_val_display,
                        "new_value_display_name": new_val_display,
                        "change_type": change_type,
                    }
                )
                most_recent_logs[field][rid] = {"old_value": old_val, "new_value": new_val}

    if logs:
        _create_audit_logs(self.env, self, logs)
        # Mark these changes as logged to prevent duplicates in the same transaction.
        for log in logs:
            field = self._fields.get(log["field_name"])
            if field:
                logged_changes[field].add(log["record_id"])

            # If this was an insert for a newly created record, mark the field as initially logged
            if log["change_type"] == "i" and log["record_id"] in newly_created:
                initially_logged.setdefault(log["record_id"], set()).add(log["field_name"])

    # Clear old_values after flush
    if "old_values" in audit_data:
        # Only clear the fields/records we just flushed
        audit_old_values = audit_data["old_values"]
        for name, field in loggable_fields_dict.items():
            if field in audit_old_values:
                field_old_values = audit_old_values[field]
                for rid in batches.get(name, []):
                    field_old_values.pop(rid, None)
                # If no more records for this field, remove the field entry
                if not field_old_values:
                    del audit_old_values[field]


models.BaseModel.create = patched_create
models.BaseModel.unlink = patched_unlink
models.BaseModel.write = patched_write
models.BaseModel._flush = patched_flush
