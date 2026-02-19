"""
Test discovery utilities.

Groups test cases from an OdooSuite by their test class so each class
(and its setUpClass data) runs entirely on a single worker. Distributes
class groups across workers using either duration-based LPT balancing
(when stats from a prior run are available) or round-robin fallback.
"""

import collections
import logging

_logger = logging.getLogger(__name__)


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


def build_batches(class_groups, worker_count, class_durations=None):
    """
    Distribute class groups across N workers.

    If class_durations (a {class_key: seconds} dict) is provided and covers
    at least some of the classes, uses Longest-Processing-Time-first (LPT)
    greedy balancing. Otherwise falls back to round-robin.

    Each batch is a list of (test_class, [test_cases]) tuples.
    Returns a list of batches, one per worker (empty batches removed).
    """
    if class_durations:
        return _build_batches_lpt(class_groups, worker_count, class_durations)
    return _build_batches_round_robin(class_groups, worker_count)


def _build_batches_round_robin(class_groups, worker_count):
    """Simple round-robin distribution (no duration data available)."""
    batches = [[] for _ in range(worker_count)]
    for i, (cls, tests) in enumerate(class_groups.items()):
        batches[i % worker_count].append((cls, tests))
    return [b for b in batches if b]


def _build_batches_lpt(class_groups, worker_count, class_durations):
    """
    Longest-Processing-Time-first greedy algorithm for makespan minimization.

    Sort classes by known duration descending, then assign each class to the
    worker with the smallest total assigned time. Classes without stats data
    get a default estimate (median of known durations, or 1s if nothing is known).
    """
    # Compute a default estimate for classes without prior stats
    known_values = [
        class_durations[f"{cls.__module__}.{cls.__qualname__}"]
        for cls in class_groups
        if f"{cls.__module__}.{cls.__qualname__}" in class_durations
    ]
    if known_values:
        default_duration = sorted(known_values)[len(known_values) // 2]  # median
    else:
        default_duration = 1.0

    # Build (class, tests, duration) list and sort by duration descending
    items = []
    for cls, tests in class_groups.items():
        key = f"{cls.__module__}.{cls.__qualname__}"
        duration = class_durations.get(key, default_duration)
        items.append((cls, tests, duration))
    items.sort(key=lambda x: x[2], reverse=True)

    # Greedily assign each class to the least-loaded worker
    worker_loads = [0.0] * worker_count
    batches = [[] for _ in range(worker_count)]
    for cls, tests, duration in items:
        lightest = min(range(worker_count), key=lambda w: worker_loads[w])
        batches[lightest].append((cls, tests))
        worker_loads[lightest] += duration

    hit = len(known_values)
    total = len(class_groups)
    _logger.info(
        "LPT balancing: %d/%d classes with stats, estimated per-worker: %.1fs..%.1fs",
        hit,
        total,
        min(worker_loads),
        max(worker_loads),
    )

    return [b for b in batches if b]
