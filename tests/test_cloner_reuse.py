"""Clone reuse key: schema + XML-ID + module version."""

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .. import cloner, config as parallel_config
from ..cloner import _reuse_key_matches, _reuse_miss_reasons


def _state(**overrides):
    payload = {
        "base_db": "cr-test",
        "fingerprint": "schema-a",
        "xmlid_fingerprint": "xmlid-a",
        "version_fingerprint": "ver-a",
        "worker_count": 2,
        "clone_names": ["cr-test-worker-0", "cr-test-worker-1"],
    }
    payload.update(overrides)
    return payload


@tagged("odoo_parallel_tests", "post_install", "-at_install", "test_cloner_reuse")
class TestCloneReuseKey(TransactionCase):
    """A value-only migration is a version bump. That bump must miss the cache."""

    def test_reuse_when_schema_xmlid_and_version_match(self):
        self.assertTrue(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
                count=2,
                clone_names=["cr-test-worker-0", "cr-test-worker-1"],
            )
        )

    def test_version_bump_invalidates_reuse(self):
        self.assertFalse(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-b",
                count=2,
                clone_names=["cr-test-worker-0", "cr-test-worker-1"],
            )
        )
        reasons = _reuse_miss_reasons(_state(), "schema-a", "xmlid-a", "ver-b", 2)
        self.assertEqual(reasons, ["module versions changed"])

    def test_schema_or_xmlid_change_still_invalidates(self):
        self.assertFalse(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-b",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
                count=2,
                clone_names=["cr-test-worker-0", "cr-test-worker-1"],
            )
        )
        self.assertFalse(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-b",
                version_fingerprint="ver-a",
                count=2,
                clone_names=["cr-test-worker-0", "cr-test-worker-1"],
            )
        )

    def test_legacy_state_without_version_does_not_reuse(self):
        legacy = _state()
        del legacy["version_fingerprint"]
        self.assertFalse(
            _reuse_key_matches(
                legacy,
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
                count=2,
                clone_names=["cr-test-worker-0", "cr-test-worker-1"],
            ),
            "Saved state from before the version key must miss, not reuse.",
        )

    def test_clone_databases_reuses_when_version_unchanged(self):
        with (
            patch.object(parallel_config, "reuse_clones", return_value=True),
            patch.object(parallel_config, "get_clone_prefix", return_value="{db}-worker-"),
            patch.object(cloner, "_can_createdb", return_value=True),
            patch.object(cloner, "_get_db_fingerprint", return_value="schema-a"),
            patch.object(cloner, "_get_xmlid_fingerprint", return_value="xmlid-a"),
            patch.object(cloner, "_get_module_version_fingerprint", return_value="ver-a"),
            patch.object(cloner, "_load_clone_state", return_value=_state()),
            patch.object(cloner, "_clones_exist", return_value=True),
            patch.object(cloner, "_fresh_clone") as fresh,
        ):
            names = cloner.clone_databases("cr-test", 2)
        fresh.assert_not_called()
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1"])

    def test_clone_databases_rebuilds_after_version_bump(self):
        with (
            patch.object(parallel_config, "reuse_clones", return_value=True),
            patch.object(parallel_config, "get_clone_prefix", return_value="{db}-worker-"),
            patch.object(cloner, "_can_createdb", return_value=True),
            patch.object(cloner, "_get_db_fingerprint", return_value="schema-a"),
            patch.object(cloner, "_get_xmlid_fingerprint", return_value="xmlid-a"),
            patch.object(cloner, "_get_module_version_fingerprint", return_value="ver-b"),
            patch.object(cloner, "_load_clone_state", return_value=_state()),
            patch.object(cloner, "_clones_exist", return_value=True),
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state") as save,
        ):
            names = cloner.clone_databases("cr-test", 2)
        fresh.assert_called_once()
        save.assert_called_once()
        self.assertEqual(save.call_args.args[3], "ver-b")
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1"])

