# test_audit_log_transaction_id_bigint.py
#
# Coverage for the 64-bit transaction id (19.0.1.598).
#
# `transaction_id` holds the PostgreSQL transaction number (`txid_current()`), a 64-bit
# counter that only grows. Declared as `fields.Integer` it was an `int4` column, and on
# 2026-09-12 production passed 2,147,483,647: every audit insert failed with
# `integer out of range`, and because the audit row is written inside the business
# transaction, every create and write in the system failed with it (white screen).
#
# A fresh test database never reaches that number, which is why no test caught it. These
# tests therefore pin the column type itself, store a number above 2^31 by hand, and run the
# migration against columns narrowed back to int4.
import importlib.util
import pathlib

from odoo.tests import TransactionCase, tagged

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1] / "migrations" / "19.0.1.598" / "pre-migrate.py"
)

# A value that does not fit in int4 (2^31 - 1 = 2,147,483,647).
_BEYOND_INT4 = 2**31 + 4242


def _load_migration():
    spec = importlib.util.spec_from_file_location("oteny_audit_bigint_19_0_1_598", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogTransactionIdBigint(TransactionCase):
    def setUp(self):
        super().setUp()
        self.migration = _load_migration()

    def _column_type(self, table):
        self.env.cr.execute(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s AND column_name = 'transaction_id'
            """,
            (table,),
        )
        return self.env.cr.fetchone()[0]

    def _view_exists(self):
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.views WHERE table_name = 'oteny_audit_log_aggregated'"
        )
        return bool(self.env.cr.fetchone())

    def test_the_columns_are_64_bit(self):
        """The field type alone must give a fresh install the wide column."""
        self.assertEqual(self._column_type("oteny_audit_log"), "int8")
        self.assertEqual(self._column_type("oteny_audit_log_ref"), "int8")

    def test_a_transaction_number_beyond_int4_is_stored_and_grouped(self):
        """The production failure, replayed: a number above 2^31 must round-trip through the
        log, the ref and the aggregated view."""
        log = (
            self.env["oteny.audit.log"]
            .sudo()
            .create(
                {
                    "model_name": "res.partner",
                    "record_id": 424242,
                    "record_display_name": "Probe",
                    "field_name": "name",
                    "change_type": "u",
                    "old_value": "before",
                    "new_value": "after",
                    "transaction_id": _BEYOND_INT4,
                }
            )
        )
        ref = (
            self.env["oteny.audit.log.ref"]
            .sudo()
            .create(
                {
                    "audit_log_id": log.id,
                    "target_model_name": "res.partner",
                    "target_record_id": 424242,
                    "is_direct": True,
                    "transaction_id": _BEYOND_INT4,
                }
            )
        )
        self.assertEqual(log.transaction_id, _BEYOND_INT4)
        self.assertEqual(ref.transaction_id, _BEYOND_INT4)

        aggregated = (
            self.env["oteny.audit.log.aggregated"]
            .sudo()
            .search([("transaction_id", "=", _BEYOND_INT4)])
        )
        self.assertTrue(aggregated, "the aggregated view must group on the wide number")
        self.assertEqual(aggregated.mapped("audit_log_id"), log)

    def test_the_migration_widens_int4_columns(self):
        """Replay the upgrade of a database that still has the narrow columns."""
        self.env.cr.execute("SELECT txid_current()")
        if self.env.cr.fetchone()[0] > 2**31 - 1:
            # A production restore already carries wide numbers; int4 cannot hold them.
            self.skipTest("this database's transaction counter is already beyond int4")

        # Narrow the columns as they were before 19.0.1.598. PostgreSQL refuses to alter a
        # column a view selects, so the view goes first, exactly as on the old schema the
        # migration meets. DDL is transactional, so the test rollback restores everything.
        self.env.cr.execute("DROP VIEW oteny_audit_log_aggregated")
        for table in ("oteny_audit_log", "oteny_audit_log_ref"):
            self.env.cr.execute(f"ALTER TABLE {table} ALTER COLUMN transaction_id TYPE int4")
            self.assertEqual(self._column_type(table), "int4")

        self.migration.migrate(self.env.cr, "19.0.1.597")

        self.assertEqual(self._column_type("oteny_audit_log"), "int8")
        self.assertEqual(self._column_type("oteny_audit_log_ref"), "int8")
        self.assertFalse(self._view_exists(), "init() rebuilds the view after the migration")

    def test_the_migration_leaves_wide_columns_alone(self):
        """On a database that is already converted (or freshly installed) the migration
        must not drop the view or touch the tables."""
        self.assertTrue(self._view_exists())

        self.migration.migrate(self.env.cr, "19.0.1.597")

        self.assertTrue(self._view_exists())
        self.assertEqual(self._column_type("oteny_audit_log"), "int8")
        self.assertEqual(self._column_type("oteny_audit_log_ref"), "int8")
