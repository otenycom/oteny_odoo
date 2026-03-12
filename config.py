"""
Configuration for the parallel test runner, read from environment variables.

All settings can be overridden per invocation via env vars.
"""

import multiprocessing
import os


def get_worker_count():
    """
    Number of parallel test workers. Defaults to 120% of CPU cores,
    with a minimum of 2 and a maximum of 32.
    """
    cores = multiprocessing.cpu_count()
    # Calculate 120% of available cores, rounding down
    calculated = max(2, int(cores * 1.2))
    default = min(32, calculated)
    return int(os.environ.get("ODOO_TEST_WORKERS", default))


def get_parallel_mode():
    """
    When to engage parallel mode:
      auto   — parallel if more than 1 test class (default)
      always — force parallel even for single class (for debugging the runner)
      never  — disable parallel, run sequentially as normal
    """
    return os.environ.get("ODOO_TEST_PARALLEL", "auto")


def get_clone_prefix():
    """Database name prefix for worker clones. {db} is replaced with the base db name."""
    return os.environ.get("ODOO_TEST_CLONE_PREFIX", "{db}-worker-")


def reuse_clones():
    """
    Whether to keep clone databases between runs and reuse them when the
    base DB schema has not changed. Defaults to True — saves ~9s on
    repeated runs. Set to false to always create fresh clones.
    """
    return os.environ.get("ODOO_TEST_REUSE_CLONES", "true").lower() not in ("false", "0", "no")


def keep_clones():
    """Legacy alias — reuse_clones supersedes this."""
    return reuse_clones()
