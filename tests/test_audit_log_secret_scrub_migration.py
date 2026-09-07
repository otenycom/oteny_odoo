# test_audit_log_secret_scrub_migration.py
#
# Coverage for migrations/19.0.1.519/post-migrate.py -- the one-off scrub of credentials
# already written into the audit log before redaction existed. A migration is forward-only
# and runs once on production, so it is tested here against seeded rows rather than trusted.
#
# The scrub must reach BOTH storage shapes. Update rows keep their value in the flat
# old_value / new_value columns; inserts and deletes keep everything in the `snapshot`
# jsonb. A scrub that fixes only the flat columns leaves every insert and delete untouched,
# and for a rotated-out system parameter the delete tombstone is exactly the row that
# preserved the old secret.
import importlib.util
import pathlib

from odoo.addons.oteny_audit.models.base_patch import AUDIT_REDACTED
from odoo.tests import TransactionCase, tagged

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1] / "migrations" / "19.0.1.519" / "post-migrate.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("oteny_audit_scrub_19_0_1_519", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogSecretScrubMigration(TransactionCase):
    """Verify the 19.0.1.519 scrub redacts stored credentials and spares everything else."""

    SECRET = "sk-legacy-DO-NOT-STORE-0123456789"
    ROTATED = "sk-legacy-ROTATED-9876543210"

    def setUp(self):
        super().setUp()
        self.log_model = self.env["oteny.audit.log"].sudo()
        self.migration = _load_migration()

    def _seed(self, **vals):
        base = {"record_id": 424242, "change_type": "u"}
        base.update(vals)
        return self.log_model.create(base)

    def _entry(self, value):
        return {"raw": value, "display": value, "label": "probe"}

    def _read_flat(self, log_id):
        self.env.cr.execute(
            "SELECT old_value, new_value, old_value_display_name, new_value_display_name "
            "FROM oteny_audit_log WHERE id = %s",
            (log_id,),
        )
        return self.env.cr.fetchone()

    def _read_snapshot(self, log_id):
        self.env.cr.execute("SELECT snapshot FROM oteny_audit_log WHERE id = %s", (log_id,))
        return self.env.cr.fetchone()[0]

    def _run(self):
        self.env.flush_all()
        return self.migration.migrate(self.env.cr, "19.0.1.518")

    # --- the field-name shape, any model --------------------------------------------- #

    def test_scrub_redacts_a_secret_named_update_row(self):
        log = self._seed(
            model_name="res.partner",
            field_name="access_token",
            old_value=self.SECRET,
            new_value=self.ROTATED,
            old_value_display_name=self.SECRET,
            new_value_display_name=self.ROTATED,
        )
        self._run()
        self.assertEqual(
            self._read_flat(log.id),
            (AUDIT_REDACTED, AUDIT_REDACTED, AUDIT_REDACTED, AUDIT_REDACTED),
        )

    def test_scrub_spares_a_plain_update_row(self):
        log = self._seed(model_name="res.partner", field_name="name", new_value="Bob")
        self._run()
        self.assertEqual(self._read_flat(log.id)[1], "Bob")

    def test_scrub_spares_a_lookup_key_field(self):
        """`cache_key` ends in `_key` and is deliberately outside the shape -- a cache key
        is not a credential, and redacting it would cost real debugging value."""
        log = self._seed(
            model_name="wilma.api.cache", field_name="cache_key", new_value="places:schiphol"
        )
        self._run()
        self.assertEqual(self._read_flat(log.id)[1], "places:schiphol")

    def test_scrub_redacts_a_secret_named_snapshot_entry(self):
        log = self._seed(
            model_name="ir.attachment",
            field_name="__snapshot__",
            change_type="i",
            snapshot={"access_token": self._entry(self.SECRET), "name": self._entry("invoice.pdf")},
        )
        self._run()
        snapshot = self._read_snapshot(log.id)
        self.assertEqual(snapshot["access_token"]["raw"], AUDIT_REDACTED)
        self.assertEqual(snapshot["access_token"]["display"], AUDIT_REDACTED)
        self.assertEqual(snapshot["access_token"]["label"], "probe", "the label must survive")
        self.assertEqual(snapshot["name"]["raw"], "invoice.pdf")

    # --- ir.config_parameter, keyed on the parameter name ---------------------------- #

    def test_scrub_redacts_a_secret_system_parameter_update_row(self):
        log = self._seed(
            model_name="ir.config_parameter",
            record_display_name="legacy.probe_api_key",
            field_name="value",
            old_value=self.SECRET,
            new_value=self.ROTATED,
        )
        self._run()
        old_value, new_value, _, _ = self._read_flat(log.id)
        self.assertEqual(old_value, AUDIT_REDACTED)
        self.assertEqual(new_value, AUDIT_REDACTED)

    def test_scrub_redacts_a_secret_system_parameter_tombstone(self):
        log = self._seed(
            model_name="ir.config_parameter",
            record_display_name="legacy.probe_token",
            field_name="__snapshot__",
            change_type="d",
            snapshot={
                "key": self._entry("legacy.probe_token"),
                "value": self._entry(self.SECRET),
            },
        )
        self._run()
        snapshot = self._read_snapshot(log.id)
        self.assertEqual(snapshot["value"]["raw"], AUDIT_REDACTED)
        self.assertEqual(
            snapshot["key"]["raw"], "legacy.probe_token", "the parameter name must survive"
        )

    def test_scrub_spares_a_plain_system_parameter(self):
        log = self._seed(
            model_name="ir.config_parameter",
            record_display_name="legacy.probe_base_url",
            field_name="value",
            new_value="https://example.test",
        )
        self._run()
        self.assertEqual(self._read_flat(log.id)[1], "https://example.test")

    # --- shape of the migration itself ------------------------------------------------ #

    def test_scrub_is_idempotent(self):
        log = self._seed(
            model_name="res.partner", field_name="access_token", new_value=self.SECRET
        )
        first = self._run()
        self.assertGreaterEqual(first, 1)
        second = self._run()
        self.assertEqual(self._read_flat(log.id)[1], AUDIT_REDACTED)
        self.assertEqual(second, 0, "a second run must find nothing left to redact")

    def test_scrub_never_deletes_a_row(self):
        """Redact, never delete -- the row, its timestamp and its user are the audit trail,
        and `_recover_unlinked_display_name` reads `record_display_name` off older rows."""
        log = self._seed(
            model_name="res.partner", field_name="access_token", new_value=self.SECRET
        )
        before = self.log_model.search_count([])
        self._run()
        self.env.invalidate_all()
        self.assertEqual(self.log_model.search_count([]), before)
        self.assertTrue(self.log_model.browse(log.id).exists())
