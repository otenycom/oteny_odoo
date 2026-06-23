# test_perf_audit_index.py
# Coverage for the audit-table index performance fix:
#   * the snapshot GIN index is now PARTIAL (WHERE field_name = '__snapshot__'),
#     so UPDATE rows (which carry no snapshot) no longer churn the GIN
#     fastupdate pending list on every insert.
#   * a composite btree (field_name, create_date DESC) backs field_name=
#     equality + create_date range lookups in the audit search.
# Both indexes are created by the models' init() at install/update time
# (committed before tests run), so the test simply inspects pg_indexes.
from odoo.tests import TransactionCase, tagged


@tagged("oteny_audit", "post_install", "-at_install", "test_perf_audit_index")
class TestPerfAuditIndex(TransactionCase):
    """Verify the audit-table indexes are in their expected (optimized) shape."""

    def test_snapshot_gin_index_is_partial(self):
        """The snapshot GIN index exists, uses GIN, and is partial on field_name."""
        self.env.cr.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE indexname = 'oteny_audit_log_snapshot_gin_idx'
            """
        )
        row = self.env.cr.fetchone()
        self.assertIsNotNone(
            row, "oteny_audit_log_snapshot_gin_idx should exist after init()"
        )
        indexdef = row[0].lower()
        # Still a GIN index over the snapshot column (the fix only narrows it).
        self.assertIn("using gin", indexdef, "snapshot index should be a GIN index")
        # A partial index records its WHERE clause in indexdef; the predicate
        # references field_name = '__snapshot__', confirming the index is partial.
        self.assertIn(
            "where",
            indexdef,
            "snapshot GIN index should be partial (carry a WHERE predicate)",
        )
        self.assertIn(
            "field_name",
            indexdef,
            "snapshot GIN index should be partial on field_name = '__snapshot__'",
        )

    def test_field_name_create_date_index_exists(self):
        """The composite btree exists and leads with (field_name, create_date)."""
        self.env.cr.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE indexname = 'oteny_audit_log_field_name_create_date_idx'
            """
        )
        row = self.env.cr.fetchone()
        self.assertIsNotNone(
            row,
            "oteny_audit_log_field_name_create_date_idx should exist after init()",
        )
        # Confirm the column order: field_name first (equality), then create_date
        # (range) — the shape that serves the audit search lookups.
        indexdef = row[0].lower()
        self.assertRegex(
            indexdef,
            r"\(field_name,\s*create_date",
            "composite index should lead with (field_name, create_date ...)",
        )
