"""The work queue: ordered, claim-once, filterable by what a worker can run."""

import os
import shutil
import tempfile

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .. import queue
from ..discovery import order_classes_longest_first


class _FakeClass:
    def __init__(self, module, name):
        self.__module__ = module
        self.__qualname__ = name


@tagged("odoo_parallel_tests", "post_install", "-at_install", "test_queue")
class TestWorkQueue(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp(prefix="hh-queue-")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def test_claims_follow_the_queue_order_and_never_repeat(self):
        qdir = queue.create_queue(self.tmpdir, ["m.A", "m.B", "m.C"])
        self.assertEqual(queue.remaining(qdir), 3)
        self.assertEqual(queue.claim_next(qdir, "0"), "m.A")
        self.assertEqual(queue.claim_next(qdir, "1"), "m.B")
        self.assertEqual(queue.claim_next(qdir, "0"), "m.C")
        self.assertIsNone(queue.claim_next(qdir, "1"))
        self.assertEqual(queue.remaining(qdir), 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmpdir, "claimed", "0"))),
                         ["0000__m.A", "0002__m.C"])

    def test_a_worker_skips_classes_it_cannot_run(self):
        qdir = queue.create_queue(self.tmpdir, ["m.A", "m.B", "m.C"])
        self.assertEqual(queue.claim_next(qdir, "0", wanted={"m.B"}), "m.B")
        self.assertIsNone(queue.claim_next(qdir, "0", wanted={"m.B"}))
        self.assertEqual(queue.remaining(qdir), 2, "A and C wait for a worker that has them")

    def test_a_lost_race_moves_on_to_the_next_entry(self):
        qdir = queue.create_queue(self.tmpdir, ["m.A", "m.B"])
        # Simulate another worker winning the rename of the first entry
        # between this worker's listdir and its rename.
        real_rename = os.rename

        def racing_rename(src, dst):
            if src.endswith("__m.A"):
                real_rename(src, os.path.join(self.tmpdir, "claimed", "other"))
                raise FileNotFoundError(src)
            return real_rename(src, dst)

        os.makedirs(os.path.join(self.tmpdir, "claimed"), exist_ok=True)
        queue.os.rename = racing_rename
        try:
            self.assertEqual(queue.claim_next(qdir, "0"), "m.B")
        finally:
            queue.os.rename = real_rename

    def test_wide_indexes_keep_lexical_order(self):
        keys = [f"m.C{i}" for i in range(12000)]
        qdir = queue.create_queue(self.tmpdir, keys)
        self.assertEqual(queue.claim_next(qdir, "0"), "m.C0")
        self.assertEqual(queue.claim_next(qdir, "0"), "m.C1")

    def test_order_is_longest_first_with_unknowns_in_the_middle(self):
        a, b, c, d = (_FakeClass("m", n) for n in "ABCD")
        groups = {a: ["ta"], b: ["tb"], c: ["tc"], d: ["td"]}
        durations = {"m.A": 5.0, "m.B": 50.0, "m.C": 20.0}  # D unknown -> median 20
        ordered = order_classes_longest_first(groups, durations)
        self.assertEqual([cls.__qualname__ for cls, _t in ordered], ["B", "C", "D", "A"])

    def test_order_without_stats_keeps_every_class(self):
        a, b = (_FakeClass("m", n) for n in "AB")
        ordered = order_classes_longest_first({a: ["ta"], b: ["tb"]}, {})
        self.assertEqual(len(ordered), 2)
