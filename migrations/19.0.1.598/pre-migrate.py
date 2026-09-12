"""Widen the audit transaction id columns to 64 bits.

Background
----------
`oteny_audit` stores the PostgreSQL transaction number (`SELECT txid_current()`)
on every audit row in `transaction_id`, so the Audit screens can group the rows
of one business action. `txid_current()` is a 64-bit counter that only grows.
The field was declared as `fields.Integer`, which Odoo maps to the SQL type
`int4` (maximum 2,147,483,647).

On 2026-09-12 at 05:30 the production database passed that number. From then
on every insert into `oteny_audit_log` failed with

    psycopg2.errors.NumericValueOutOfRange: integer out of range

The audit rows are written inside the business transaction, so every create and
write in the system failed with them. The first backend page load after the
2026-09-11 deploy had to rebuild the web client asset bundles, which are
`ir.attachment` rows; that insert failed too, the bundles returned HTTP 500 and
every user saw a white screen. The test1 and test2 branches restore from
production and carried the same counter, so they failed the same way.

What it does
------------
Converts `transaction_id` to `bigint` on `oteny_audit_log` and
`oteny_audit_log_ref`. The SQL view `oteny_audit_log_aggregated` selects the
column, and PostgreSQL refuses to change the type of a column a view depends
on, so the view is dropped first. The module's `init()` recreates the view
right after this migration, during the same upgrade.

The models now declare the field as `BigInteger` (`int8`), so Odoo's own
column check would perform the same conversion. This migration does it
explicitly and earlier, so the upgrade log names the repair and the conversion
runs before any model of the module is initialised. Both paths are idempotent:
a column that is already `bigint` is left alone.

Cost
----
`ALTER COLUMN ... TYPE bigint` rewrites the table and rebuilds the index on
`transaction_id`. On production the two tables hold about 2.4 GB, so expect a
few minutes with the audit tables locked. Nothing else is locked.
"""

import logging

_logger = logging.getLogger(__name__)

_TABLES = ("oteny_audit_log", "oteny_audit_log_ref")
_VIEW = "oteny_audit_log_aggregated"


def _column_type(cr, table, column):
    cr.execute(
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cr.fetchone()
    return row[0] if row else None


def migrate(cr, version):
    to_convert = [t for t in _TABLES if _column_type(cr, t, "transaction_id") == "int4"]
    if not to_convert:
        _logger.info("transaction_id is already 64-bit on %s; nothing to do", ", ".join(_TABLES))
        return

    # The aggregated view selects transaction_id from oteny_audit_log, and PostgreSQL
    # refuses to alter a column a view depends on. The module's init() rebuilds the view.
    cr.execute(f"DROP VIEW IF EXISTS {_VIEW}")
    for table in to_convert:
        _logger.info("Converting %s.transaction_id from int4 to bigint", table)
        cr.execute(f"ALTER TABLE {table} ALTER COLUMN transaction_id TYPE bigint")
    _logger.info("transaction_id is now bigint on %s", ", ".join(to_convert))
