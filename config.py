"""
Configuration for the parallel test runner, read from environment variables.

All settings can be overridden per invocation via env vars.
"""

import multiprocessing
import os


def get_worker_count():
    """Number of parallel test workers. Defaults to half CPU cores, min 2, max 8."""
    default = min(8, max(2, multiprocessing.cpu_count() // 2))
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


def keep_clones():
    """Whether to keep cloned databases after the run (useful for debugging)."""
    return os.environ.get("ODOO_TEST_KEEP_CLONES", "false").lower() in ("true", "1", "yes")
