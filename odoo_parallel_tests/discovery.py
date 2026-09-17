"""
Test discovery utilities.

Groups test cases from an OdooSuite by their test class so each class
(and its setUpClass data) runs entirely on a single worker, and orders the
classes for the work queue: longest first, from the timing stats of prior
runs, so the big classes start early and the small ones fill the tail.
"""

import collections
import logging

_logger = logging.getLogger(__name__)


def get_test_class_key(test):
    """Unique string key for a test's class: module.qualname."""
    cls = type(test)
    return f"{cls.__module__}.{cls.__qualname__}"


def class_key(cls):
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


def order_classes_longest_first(class_groups, class_durations=None):
    """
    The queue order: classes sorted by estimated duration, longest first.

    With a queue the estimates only decide the order, not the assignment,
    so a stale or missing estimate costs little. A class without stats gets
    the median of the known durations (or 1s when nothing is known), which
    puts it in the middle of the queue rather than at either end.

    Returns a list of (test_class, [test_cases]) tuples.
    """
    class_durations = class_durations or {}
    known = [class_durations[class_key(cls)] for cls in class_groups if class_key(cls) in class_durations]
    default_duration = sorted(known)[len(known) // 2] if known else 1.0

    items = [
        (cls, tests, class_durations.get(class_key(cls), default_duration))
        for cls, tests in class_groups.items()
    ]
    items.sort(key=lambda x: x[2], reverse=True)

    total = sum(d for _cls, _tests, d in items)
    _logger.info(
        "Queue order: %d/%d classes with stats, %.1fs estimated in total, longest %.1fs",
        len(known), len(class_groups), total, items[0][2] if items else 0.0,
    )
    return [(cls, tests) for cls, tests, _d in items]
