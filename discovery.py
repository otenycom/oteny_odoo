"""
Test discovery utilities.

Groups test cases from an OdooSuite by their test class so each class
(and its setUpClass data) runs entirely on a single worker. Distributes
class groups across workers using round-robin.
"""

import collections


def get_test_class_key(test):
    """Unique string key for a test's class: module.qualname."""
    cls = type(test)
    return f"{cls.__module__}.{cls.__qualname__}"


def group_tests_by_class(suite):
    """
    Group tests in the suite by their class.

    Returns an ordered dict of {test_class: [test_case, ...]} preserving the
    original insertion order (which is the sorted test_sequence order from
    make_suite).
    """
    groups = collections.OrderedDict()
    for test in suite:
        cls = type(test)
        groups.setdefault(cls, []).append(test)
    return groups


def build_batches(class_groups, worker_count):
    """
    Distribute class groups across N workers using round-robin.

    Each batch is a list of (test_class, [test_cases]) tuples.
    Returns a list of batches, one per worker (empty batches removed).
    """
    batches = [[] for _ in range(worker_count)]
    for i, (cls, tests) in enumerate(class_groups.items()):
        batches[i % worker_count].append((cls, tests))
    return [b for b in batches if b]
