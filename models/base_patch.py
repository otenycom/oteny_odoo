# audit_log/models/base_patch.py
from collections import defaultdict
from odoo import models, api
from odoo.tools import SQL

original_create = models.BaseModel.create
original_unlink = models.BaseModel.unlink
original_write = models.BaseModel.write
original_flush = models.BaseModel._flush


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
            for col in columns:
                field = model_fields[col]
                raw_val = new_values.get(record.id, {}).get(col)
                new_val_cached = field.convert_to_cache(raw_val, record) if raw_val is not None else None

                if new_val_cached is None:
                    continue

                if field.default:
                    default_value = field.default(record)
                    default_value_cached = field.convert_to_cache(default_value, record)
                    if new_val_cached == default_value_cached:
                        continue

                new_val_display = _get_display_value(field, new_val_cached, record.env)

                logs.append(
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
                        "change_type": "insert",
                    }
                )
        if logs:
            self.env.cr.execute("SELECT txid_current()")
            txid = self.env.cr.fetchone()[0]
            for log in logs:
                log["transaction_id"] = txid
            self.env["oteny.audit.log"].sudo().create(logs)

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
        for col in columns:
            field = model_fields[col]
            raw_val = old_values.get(record.id, {}).get(col)
            old_val = field.convert_to_cache(raw_val, record) if raw_val is not None else None
            old_val_display = _get_display_value(field, old_val, record.env)
            logs.append(
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
                    "change_type": "delete",
                }
            )
    if logs:
        self.env.cr.execute("SELECT txid_current()")
        txid = self.env.cr.fetchone()[0]
        for log in logs:
            log["transaction_id"] = txid
        self.env["oteny.audit.log"].sudo().create(logs)

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
        if not hasattr(self.env, "_audit_old_values"):
            self.env._audit_old_values = defaultdict(dict)

        # If a field is written to again, it should be logged again.
        # We remove it from the logged_changes cache to allow the next flush to process it.
        if hasattr(self.env, "_audit_logged_changes"):
            logged_changes = self.env._audit_logged_changes
            for field in scalar_fields.values():
                if field in logged_changes:
                    # Remove the records being written from the set of logged changes for this field.
                    logged_changes[field] -= set(self.ids)

        dirty_fields = self.env.cache._dirty
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
            self.browse(list(records_to_read_ids)).read(list(scalar_fields.keys()))

        for record in self:
            for name, field in scalar_fields.items():
                # Check if this field is already dirty for this record
                if record.id not in dirty_fields.get(field, set()):
                    # First modification: capture old value from cache if present
                    if self.env.cache.contains(record, field):
                        old_val = self.env.cache.get(record, field)
                        self.env._audit_old_values[field][record.id] = old_val

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
                    old_records = self.env[field.comodel_name].browse(old_ids)
                    new_records = self.env[field.comodel_name].browse(new_ids)

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
                            "change_type": "update",
                        }
                    )
        if logs:
            if self.env.registry.loaded:
                self.env.cr.execute("SELECT txid_current()")
                txid = self.env.cr.fetchone()[0]
                for log in logs:
                    log["transaction_id"] = txid
                self.env["oteny.audit.log"].sudo().create(logs)

    return result


def patched_flush(self, fnames=None):
    """
    Patched flush method that captures changes and logs them to audit table.
    Compatible with Odoo 18's flush signature.
    """
    # Bypass if model is not yet fully loaded, or for the audit log model itself
    if not self.env.registry.loaded or self.env["oteny.audit.log"]._is_audit_ignored(self._name):
        return original_flush(self, fnames)

    # Use a transaction-level cache to prevent duplicate logging within the same transaction.
    if not hasattr(self.env, "_audit_logged_changes"):
        self.env._audit_logged_changes = defaultdict(set)
    logged_changes = self.env._audit_logged_changes

    records = self

    # Get dirty fields from cache
    dirty_fields_dict = self.env.cache._dirty

    # Determine all fields of the current model that are dirty, regardless of `fnames`.
    # The original_flush will clear all of them from the cache, so we must audit all of them.
    all_dirty_model_fields = {
        field
        for field, dirty_ids in dirty_fields_dict.items()
        if field.model_name == self._name and dirty_ids
    }

    if not all_dirty_model_fields:
        # No dirty fields for this model to worry about.
        return original_flush(self, fnames)

    # Filter for fields that we can and should log (not readonly).
    loggable_fields_dict = {field.name: field for field in all_dirty_model_fields if not field.readonly}

    if not loggable_fields_dict:
        return original_flush(self, fnames)

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
        return original_flush(self, fnames)

    # Get display names for all affected records
    display_names = {}
    for rec in self.browse(all_ids):
        try:
            display_names[rec.id] = rec.display_name
        except Exception:
            display_names[rec.id] = f"ID: {rec.id}"

    # Collect old values
    old_values = {}
    missing_queries = defaultdict(list)  # field: [ids needing DB query]

    # First try to get old values from our saved env._audit_old_values
    if hasattr(self.env, "_audit_old_values"):
        for name in loggable_fields_dict:
            field = loggable_fields_dict[name]
            for rid in batches.get(name, []):
                if field in self.env._audit_old_values and rid in self.env._audit_old_values[field]:
                    old_values.setdefault(rid, {})[name] = self.env._audit_old_values[field][rid]
                else:
                    # Need to query the database for the old value
                    missing_queries[field].append(rid)
    else:
        # No saved old values, need to query all from database
        for name, field in loggable_fields_dict.items():
            for rid in batches.get(name, []):
                missing_queries[field].append(rid)

    # Query database for missing old values
    for field, miss_ids in missing_queries.items():
        if miss_ids and field.column_type:
            query = SQL(
                "SELECT id, %s FROM %s WHERE id IN %s",
                SQL.identifier(field.name),
                SQL.identifier(self._table),
                tuple(miss_ids),
            )
            self.env.cr.execute(query)
            db_data = self.env.cr.dictfetchall()
            for row in db_data:
                record = self.browse(row["id"])
                val = field.convert_to_cache(row[field.name], record)
                old_values.setdefault(row["id"], {})[field.name] = val

    # Perform original flush
    original_flush(self, fnames)

    # Log changes using old_values
    logs = []
    for name in loggable_fields_dict:
        field = loggable_fields_dict[name]
        for rid in batches.get(name, []):
            record = self.browse(rid)
            old_val = old_values.get(rid, {}).get(name)
            # Get new value from cache (it might still be there after flush)
            try:
                if field.column_type:
                    # For simple fields, try cache then direct SQL for performance
                    new_val = self.env.cache.get(record, field, None)
                    if new_val is None:
                        query = SQL(
                            "SELECT %s FROM %s WHERE id = %s",
                            SQL.identifier(field.name),
                            SQL.identifier(self._table),
                            rid,
                        )
                        self.env.cr.execute(query)
                        result = self.env.cr.fetchone()
                        db_val = result[0] if result else None
                        new_val = field.convert_to_cache(db_val, record) if db_val is not None else None
                else:
                    # For relational fields (m2m, o2m), read from recordset
                    new_val_from_rec = record[name]
                    new_val = field.convert_to_cache(new_val_from_rec, record)
            except Exception:
                new_val = None

            if old_val != new_val:
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
                        "change_type": "update",
                    }
                )

    if logs:
        if self.env.registry.loaded:
            self.env.cr.execute("SELECT txid_current()")
            txid = self.env.cr.fetchone()[0]
            for log in logs:
                log["transaction_id"] = txid
            self.env["oteny.audit.log"].sudo().create(logs)
            # Mark these changes as logged to prevent duplicates in the same transaction.
            for log in logs:
                field = self._fields.get(log["field_name"])
                if field:
                    logged_changes[field].add(log["record_id"])

    # Clear old_values after flush
    if hasattr(self.env, "_audit_old_values"):
        # Only clear the fields/records we just flushed
        for name, field in loggable_fields_dict.items():
            if field in self.env._audit_old_values:
                for rid in batches.get(name, []):
                    self.env._audit_old_values[field].pop(rid, None)
                # If no more records for this field, remove the field entry
                if not self.env._audit_old_values[field]:
                    del self.env._audit_old_values[field]


models.BaseModel.create = patched_create
models.BaseModel.unlink = patched_unlink
models.BaseModel.write = patched_write
models.BaseModel._flush = patched_flush
