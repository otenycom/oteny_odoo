# test_audit_log_orphan_repair_migration.py
#
# Coverage for migrations/19.0.1.519/pre-migrate.py -- the repair of rows whose cascade
# parent is gone. `pg_restore` loads data before constraints, so anything deleting parents in
# that window leaves orphans the foreign key can then never tolerate: `ALTER TABLE ... ADD
# FOREIGN KEY` fails, the registry fails to load, and the database cannot be upgraded again.
#
# Proven on a real recovery of `crmain` on 2026-08-25 (78,297 orphan oteny_audit_log_ref rows,
# then 64 discuss_channel_member and 3 documents_access). This pins the behaviour so the
# repair cannot regress, and so a new entry added to _CASCADE_REFERENCES is exercised.
import importlib.util
import pathlib

from odoo.tests import TransactionCase, tagged

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1] / "migrations" / "19.0.1.519" / "pre-migrate.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("oteny_audit_repair_19_0_1_519", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogOrphanRepairMigration(TransactionCase):
    """Verify the 19.0.1.519 pre-migration deletes orphans and spares everything else."""

    def setUp(self):
        super().setUp()
        self.log_model = self.env["oteny.audit.log"].sudo()
        self.ref_model = self.env["oteny.audit.log.ref"].sudo()
        self.migration = _load_migration()

    def _make_ref(self, audit_log_id):
        ref = self.ref_model.create(
            {
                "audit_log_id": audit_log_id,
                "target_model_name": "res.partner",
                "target_record_id": 424242,
                "is_direct": True,
            }
        )
        self.env.flush_all()
        return ref

    def _make_log(self):
        log = self.log_model.create(
            {
                "model_name": "res.partner",
                "record_id": 424242,
                "field_name": "name",
                "change_type": "u",
                "new_value": "probe",
            }
        )
        self.env.flush_all()
        return log

    def _exists(self, ref_id):
        self.env.cr.execute("SELECT 1 FROM oteny_audit_log_ref WHERE id = %s", (ref_id,))
        return bool(self.env.cr.fetchone())

    def test_an_orphan_ref_is_deleted(self):
        """The foreign key is created ON DELETE cascade, so this row cannot exist while the
        constraint does. It exists only because the parent went while the key was absent."""
        log = self._make_log()
        ref = self._make_ref(log.id)
        # Reproduce the restore window: remove the parent with the constraint out of the way.
        self.env.cr.execute(
            "ALTER TABLE oteny_audit_log_ref DROP CONSTRAINT oteny_audit_log_ref_audit_log_id_fkey"
        )
        self.env.cr.execute("DELETE FROM oteny_audit_log WHERE id = %s", (log.id,))
        self.assertTrue(self._exists(ref.id), "the orphan must exist before the repair")

        self.migration.migrate(self.env.cr, "19.0.1.494")

        self.assertFalse(self._exists(ref.id))

    def test_a_ref_whose_parent_still_exists_survives(self):
        """The control. The repair must not touch a live audit trail."""
        log = self._make_log()
        ref = self._make_ref(log.id)

        self.migration.migrate(self.env.cr, "19.0.1.494")

        self.assertTrue(self._exists(ref.id))

    def test_the_foreign_key_can_be_added_again_after_the_repair(self):
        """The point of the whole exercise: without this, every later upgrade fails."""
        log = self._make_log()
        self._make_ref(log.id)
        self.env.cr.execute(
            "ALTER TABLE oteny_audit_log_ref DROP CONSTRAINT oteny_audit_log_ref_audit_log_id_fkey"
        )
        self.env.cr.execute("DELETE FROM oteny_audit_log WHERE id = %s", (log.id,))

        self.migration.migrate(self.env.cr, "19.0.1.494")

        self.env.cr.execute(
            "ALTER TABLE oteny_audit_log_ref ADD CONSTRAINT "
            "oteny_audit_log_ref_audit_log_id_fkey FOREIGN KEY (audit_log_id) "
            "REFERENCES oteny_audit_log(id) ON DELETE cascade"
        )

    def test_repair_is_idempotent(self):
        self.migration.migrate(self.env.cr, "19.0.1.494")
        self.migration.migrate(self.env.cr, "19.0.1.494")

    def test_every_declared_reference_names_real_columns(self):
        """A typo in _CASCADE_REFERENCES would make the repair silently skip a table, and the
        upgrade would fail on the foreign key it was meant to unblock."""
        for child, column, parent, parent_column in self.migration._CASCADE_REFERENCES:
            self.env.cr.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (child,)
            )
            columns = {row[0] for row in self.env.cr.fetchall()}
            if not columns:
                continue  # module not installed in this database
            self.assertIn(column, columns, f"{child}.{column}")
            self.env.cr.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (parent,)
            )
            parent_columns = {row[0] for row in self.env.cr.fetchall()}
            self.assertTrue(parent_columns, f"{parent} missing while {child} exists")
            self.assertIn(parent_column, parent_columns, f"{parent}.{parent_column}")
