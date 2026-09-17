"""Clone pool: reuse keyed on schema + XML-ID + module version, not on count."""

import contextlib
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


@contextlib.contextmanager
def _pool(existing, state=None):
    """The patches every clone_databases test needs, around a given pool:
    reuse on, unchanged fingerprints, and ``existing`` as the databases
    that still exist on the server."""
    with contextlib.ExitStack() as stack:
        for cm in (
            patch.object(parallel_config, "reuse_clones", return_value=True),
            patch.object(parallel_config, "get_clone_prefix", return_value="{db}-worker-"),
            patch.object(cloner, "_can_createdb", return_value=True),
            patch.object(cloner, "_get_db_fingerprint", return_value="schema-a"),
            patch.object(cloner, "_get_xmlid_fingerprint", return_value="xmlid-a"),
            patch.object(cloner, "_get_module_version_fingerprint", return_value="ver-a"),
            patch.object(cloner, "_load_clone_state", return_value=state or _state()),
            patch.object(cloner, "_existing_databases", return_value=set(existing)),
            patch.object(cloner, "has_filestore_replica", return_value=True),
        ):
            stack.enter_context(cm)
        yield


@tagged("odoo_parallel_tests", "post_install", "-at_install", "test_cloner_reuse")
class TestCloneReuseKey(TransactionCase):
    """A value-only migration is a version bump. That bump must miss the cache.
    A different worker count must NOT."""

    def test_reuse_when_schema_xmlid_and_version_match(self):
        self.assertTrue(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
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
            )
        )
        reasons = _reuse_miss_reasons(_state(), "schema-a", "xmlid-a", "ver-b")
        self.assertEqual(reasons, ["module versions changed"])

    def test_schema_or_xmlid_change_still_invalidates(self):
        self.assertFalse(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-b",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
            )
        )
        self.assertFalse(
            _reuse_key_matches(
                _state(),
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-b",
                version_fingerprint="ver-a",
            )
        )

    def test_legacy_state_without_version_does_not_reuse(self):
        state = _state()
        del state["version_fingerprint"]
        self.assertFalse(
            _reuse_key_matches(
                state,
                base_db="cr-test",
                fingerprint="schema-a",
                xmlid_fingerprint="xmlid-a",
                version_fingerprint="ver-a",
            )
        )

    def test_clone_databases_reuses_when_version_unchanged(self):
        with (
            _pool(["cr-test-worker-0", "cr-test-worker-1"]),
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state"),
        ):
            names = cloner.clone_databases("cr-test", 2)
        fresh.assert_not_called()
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1"])

    def test_fewer_workers_reuse_a_subset_and_keep_the_pool(self):
        # The subset run: 1 worker wanted, 2 valid clones in the pool.
        with (
            _pool(["cr-test-worker-0", "cr-test-worker-1"]),
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state") as save,
            patch.object(cloner, "drop_databases") as drop,
        ):
            names = cloner.clone_databases("cr-test", 1)
        fresh.assert_not_called()
        drop.assert_not_called()
        self.assertEqual(names, ["cr-test-worker-0"])
        # The pool keeps both clones for the next bigger run.
        self.assertEqual(save.call_args.args[4], ["cr-test-worker-0", "cr-test-worker-1"])

    def test_more_workers_create_only_the_missing_clones(self):
        with (
            _pool(["cr-test-worker-0", "cr-test-worker-1"]),
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state") as save,
        ):
            names = cloner.clone_databases("cr-test", 3)
        fresh.assert_called_once_with("cr-test", ["cr-test-worker-2"])
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1", "cr-test-worker-2"])
        self.assertEqual(
            save.call_args.args[4],
            ["cr-test-worker-0", "cr-test-worker-1", "cr-test-worker-2"],
        )

    def test_a_pool_clone_dropped_by_hand_is_recreated(self):
        with (
            _pool(["cr-test-worker-0"]),  # worker-1 is gone from the server
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state"),
        ):
            names = cloner.clone_databases("cr-test", 2)
        fresh.assert_called_once_with("cr-test", ["cr-test-worker-1"])
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1"])

    def test_clone_databases_rebuilds_after_version_bump(self):
        state = _state(clone_names=["cr-test-worker-0", "cr-test-worker-1", "cr-test-worker-2"])
        with (
            _pool(["cr-test-worker-0", "cr-test-worker-1", "cr-test-worker-2"], state=state),
            patch.object(cloner, "_get_module_version_fingerprint", return_value="ver-b"),
            patch.object(cloner, "_fresh_clone") as fresh,
            patch.object(cloner, "_save_clone_state") as save,
            patch.object(cloner, "drop_databases") as drop,
        ):
            names = cloner.clone_databases("cr-test", 2)
        # The whole stale pool goes: the two needed are recreated, the extra dropped.
        fresh.assert_called_once_with("cr-test", ["cr-test-worker-0", "cr-test-worker-1"])
        drop.assert_called_once_with(["cr-test-worker-2"])
        save.assert_called_once()
        self.assertEqual(save.call_args.args[3], "ver-b")
        self.assertEqual(names, ["cr-test-worker-0", "cr-test-worker-1"])


@tagged("odoo_parallel_tests", "post_install", "-at_install", "test_cloner_strategy")
class TestCloneStrategy(TransactionCase):
    """PostgreSQL 15+ copies files; older servers keep createdb -T."""

    def test_file_copy_on_postgres_15_and_later(self):
        with (
            patch.object(cloner, "_server_version_num", return_value=180003),
            patch.object(cloner, "_get_pg_args", return_value=["-U", "ries"]),
        ):
            cmd = cloner._create_database_cmd("cr-test", "cr-test-worker-0")
        self.assertEqual(cmd[0], "psql")
        self.assertIn("-U", cmd)
        self.assertEqual(
            cmd[-1],
            'CREATE DATABASE "cr-test-worker-0" TEMPLATE "cr-test" STRATEGY = FILE_COPY;',
        )

    def test_createdb_before_postgres_15(self):
        with (
            patch.object(cloner, "_server_version_num", return_value=140011),
            patch.object(cloner, "_get_pg_args", return_value=[]),
        ):
            cmd = cloner._create_database_cmd("cr-test", "cr-test-worker-0")
        self.assertEqual(cmd, ["createdb", "-T", "cr-test", "cr-test-worker-0"])
