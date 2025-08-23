# Audit Log Module for Odoo 18

## Overview

This module provides comprehensive audit logging for Odoo 18, capturing all database changes (CREATE, UPDATE, DELETE) during the ORM flush cycle.

## Implementation Details

### 1. Patched Methods

- __`patched_create`__: Logs INSERT operations
- __`patched_write`__: Captures old values before modifications  
- __`patched_flush`__: Logs UPDATE operations during flush
- __`patched_unlink`__: Logs DELETE operations

### 2. Old Value Tracking

Old values are stored on the environment (`env._audit_prev_values`) as a nested dictionary:

```python
{
    field_object: {
        record_id: prev_value
    }
}
```

### 3. Dirty Field Detection

Uses Odoo 18's cache API to detect dirty fields:

```python
dirty_fields_dict = self.env.cache._dirty  # Dictionary of {field: set(record_ids)}
```

### 4. Recursion Prevention

The audit log model itself is excluded from logging to prevent infinite loops:

```python
if self._name == "oteny.audit.log":
    return original_method(self, ...)
```

## Files Structure

```
oteny_audit/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── base_patch.py        # Core audit logging implementation
│   └── oteny_audit_log.py   # Audit log model definition
├── security/
│   └── ir.model.access.csv  # Access rights
├── tests/
│   ├── __init__.py
│   └── test_audit_log.py    # Unit tests
└── README_AUDIT_LOG.md      # This file
```

## Testing

Run tests with:

```bash
./odoo-bin -c <config_file> -d <database> -i oteny_audit --test-enable --stop-after-init
```

## Key Differences from Standard Approaches

1. __Environment-based storage__: Uses `env._audit_prev_values` instead of trying to modify the slotted Transaction class
2. __Compatible with Odoo 18__: Uses the correct `_flush(self, fnames=None)` signature
3. __Efficient batching__: Minimizes database queries by batching old value lookups
4. __Proper cleanup__: Clears old values after flush to prevent memory leaks

## Known Limitations

- Only tracks stored fields with column types
- Does not track computed fields (unless stored)
- Translation and company-dependent fields are not currently audited

## Future Enhancements

- Add support for translated fields
- Add support for company-dependent fields  
- Implement audit log filtering/configuration
- Add audit log UI views for browsing history
