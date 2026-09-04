"""
Configuration for the parallel test runner, read from environment variables.

All settings can be overridden per invocation via env vars.
"""

import multiprocessing
import os


def get_worker_count():
    """
    Number of parallel test workers. Defaults to the CPU core count, with a
    minimum of 2 and a maximum of 32.

    With the work queue every worker stays busy until the queue is empty,
    so more workers than cores only add contention: on a 16-core machine
    the full suite took 108.8 s with 19 workers (120% of cores, the old
    default) and 69.7 s with 16, because the biggest class ran 92 s under
    19 workers and 52 s under 16. Static batches used to hide this: the
    early finishers thinned the load over the last third of the run.
    """
    cores = multiprocessing.cpu_count()
    default = min(32, max(2, cores))
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
    base DB schema, XML IDs, and module versions have not changed.
    Defaults to True — saves ~9s on repeated runs. Set to false to
    always create fresh clones.
    """
    return os.environ.get("ODOO_TEST_REUSE_CLONES", "true").lower() not in ("false", "0", "no")


def keep_clones():
    """Legacy alias — reuse_clones supersedes this."""
    return reuse_clones()
