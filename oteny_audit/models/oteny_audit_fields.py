# oteny_audit/models/oteny_audit_fields.py
"""Field types private to the audit module.

Why a 64-bit integer field exists here
--------------------------------------
Every audit row carries the PostgreSQL transaction number it was written in
(`transaction_id`, filled from `SELECT txid_current()` in `base_patch`), so the
Audit screens can group the rows of one business action together. That number
is a 64-bit counter that only grows for the life of a database. Odoo's own
`fields.Integer` maps to the SQL type `int4`, which stops at 2,147,483,647.

On 2026-09-12 the production database passed that number. From that moment
every insert into `oteny_audit_log` failed with `integer out of range`, and
because the audit rows are written inside the business transaction, every
create and write in the whole system failed with it. The web client could not
even rebuild its asset bundles (those are `ir.attachment` rows), so users saw
a white screen.

`BigInteger` is `fields.Integer` with the column type `int8`. Odoo compares
the column type on module update and converts the column itself
(`Field.update_db_column`), so a fresh install and a plain `-u` both end with
a 64-bit column. The 19.0.1.598 pre-migration does the same conversion
explicitly and earlier, so the repair is visible in the upgrade log and runs
before any model of the module is touched.

The subclass keeps `type = "integer"`, so the web client, the ORM search
operators and `ir.model.fields` treat it as an ordinary integer. Odoo
registers field classes by type with `setdefault`, so this subclass never
replaces the core `integer` class.
"""

from odoo import fields


class BigInteger(fields.Integer):
    """A 64-bit integer column (`int8`) that behaves as an Integer everywhere else."""

    _column_type = ("int8", "int8")
