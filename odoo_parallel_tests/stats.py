"""
Per-class test duration statistics for balanced worker distribution.

Persists a JSON file of {class_key: seconds} across runs. Each run
merges its results into the file — only keys for classes that actually
ran are overwritten, all other keys are preserved. This makes the data
resilient across different --test-tags invocations (e.g. running
"test_salary" updates salary entries without erasing billing data).
"""

import collections
import json
import logging
import os

_logger = logging.getLogger(__name__)

DEFAULT_STATS_PATH = "/tmp/odoo_parallel_test_stats.json"


def get_stats_path():
    return os.environ.get("ODOO_TEST_STATS_FILE", DEFAULT_STATS_PATH)


def load_stats():
    """
    Load per-class durations from the stats file.
    Returns {class_key: seconds} dict, empty if the file is missing or corrupt.
    """
    path = get_stats_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        _logger.warning("Stats file has unexpected format, ignoring")
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        _logger.warning("Could not load stats from %s: %s", path, exc)
        return {}


def save_stats(new_durations):
    """
    Merge new_durations into the existing stats file (load-merge-write).
    Only keys present in new_durations are updated; all other entries
    from prior runs are preserved.
    """
    path = get_stats_path()
    existing = load_stats()
    existing.update(new_durations)
    try:
        with open(path, "w") as f:
            json.dump(existing, f, indent=2, sort_keys=True)
        _logger.info(
            "Saved stats for %d classes (%d updated) to %s",
            len(existing),
            len(new_durations),
            path,
        )
    except OSError as exc:
        _logger.warning("Could not write stats to %s: %s", path, exc)


def extract_class_durations(result):
    """
    Aggregate per-test timing from an OdooTestResult into per-class totals.

    result.stats keys look like:
      odoo.addons.crewradar.tests.test_billing.TestBilling.test_method
      odoo.addons.crewradar.tests.test_billing.TestBilling.setUpClass

    The class key is everything up to the last dot (the method/setup name).
    We sum Stat.time values for all entries sharing the same class prefix.
    """
    durations = collections.defaultdict(float)
    for test_id, stat in result.stats.items():
        # Class key = test_id minus the last ".method_name" segment
        dot = test_id.rfind(".")
        if dot > 0:
            class_key = test_id[:dot]
            durations[class_key] += stat.time
    return dict(durations)
