"""
Monkey-patch for Odoo's test loader to enable parallel test execution.

Applied on module import (via __init__.py). Patches loader.run_suite to:
  - In master mode: detect multiple test classes, clone DB, spawn workers
  - In worker mode: filter the suite to assigned classes and run sequentially

Only parallelizes during the post-install test phase (not at-install),
detected by checking the call stack for load_module_graph.
"""

import inspect
import json
import logging
import os
import sys
import time

from . import config
from .discovery import get_test_class_key, group_tests_by_class, build_batches

_logger = logging.getLogger(__name__)

# The original run_suite function, saved before patching
_original_run_suite = None


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------


def _is_post_install_phase():
    """
    Determine whether run_suite is being called from the post-install test
    phase (directly from preload_registries) vs the at-install phase (from
    inside load_module_graph during module loading).

    At-install call stack:
      preload_registries → Registry.new → load_modules → load_module_graph
        → loader.run_suite

    Post-install call stack:
      preload_registries → loader.run_suite

    We walk the call stack looking for load_module_graph. If found, we are
    in at-install and must NOT parallelize (the DB is still being modified).
    """
    frame = inspect.currentframe()
    try:
        frame = frame.f_back  # _patched_run_suite
        while frame:
            if frame.f_code.co_name == "load_module_graph":
                return False
            frame = frame.f_back
        return True
    finally:
        del frame


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def _should_parallelize(suite):
    """Check config and suite contents to decide if we should parallelize."""
    mode = config.get_parallel_mode()
    if mode == "never":
        return False

    classes = set()
    for test in suite:
        classes.add(get_test_class_key(test))

    if mode == "always":
        return len(classes) >= 1

    # auto: parallelize when there are multiple test classes
    return len(classes) > 1


# ---------------------------------------------------------------------------
# Worker mode: filter suite to the assigned batch and run
# ---------------------------------------------------------------------------


def _worker_run(suite, batch_spec, global_report):
    """
    Called in a worker subprocess. Filters the discovered suite to only
    the test classes assigned to this worker, runs them with the original
    run_suite, and writes results to a JSON file for the master to read.
    """
    from odoo.tests.suite import OdooSuite
    from odoo.tests.result import OdooTestResult

    allowed = set(batch_spec.split(","))
    filtered = [t for t in suite if get_test_class_key(t) in allowed]

    if not filtered:
        _logger.info("Worker: no matching tests for batch — skipping")
        return OdooTestResult()

    _logger.info(
        "Worker running %d tests from %d classes",
        len(filtered),
        len(allowed),
    )

    filtered_suite = OdooSuite(filtered)
    result = _original_run_suite(filtered_suite, global_report=global_report)

    # Write structured result for the master process, including per-class
    # timing so the master can update the stats file for future balancing
    result_file = os.environ.get("ODOO_PARALLEL_RESULT")
    if result_file:
        from .stats import extract_class_durations

        with open(result_file, "w") as f:
            json.dump(
                {
                    "failures_count": result.failures_count,
                    "errors_count": result.errors_count,
                    "testsRun": result.testsRun,
                    "skipped": result.skipped,
                    "class_durations": extract_class_durations(result),
                },
                f,
            )

    return result


# ---------------------------------------------------------------------------
# Master mode: orchestrate parallel execution
# ---------------------------------------------------------------------------


def _parallel_run(suite, global_report):
    """
    Master-side parallel execution. Discovers test classes, clones the
    database for each worker, spawns worker subprocesses, waits for them,
    and aggregates results back into an OdooTestResult.
    """
    from .cloner import clone_databases, drop_databases
    from .runner import spawn_workers, wait_for_workers
    from odoo.tests.result import OdooTestResult
    from odoo import tools

    db_name = tools.config["db_name"]
    # Odoo stores db_name as a list; take the first (and typically only) entry
    if isinstance(db_name, (list, tuple)):
        db_name = db_name[0]
    worker_count = config.get_worker_count()

    # Discover test classes and distribute into batches
    class_groups = group_tests_by_class(suite)
    total_tests = suite.countTestCases()
    _logger.info(
        "Parallel test runner: %d classes, %d tests, requesting %d workers",
        len(class_groups),
        total_tests,
        worker_count,
    )

    # Load prior timing stats for duration-based balancing (LPT);
    # falls back to round-robin if no stats file exists yet
    from .stats import load_stats, save_stats

    class_durations = load_stats()

    batches = build_batches(class_groups, worker_count, class_durations)
    actual_workers = len(batches)
    if actual_workers < worker_count:
        _logger.info(
            "Using %d workers (fewer classes than requested)", actual_workers
        )

    # Build batch specs: comma-separated qualified class names per worker
    batch_specs = []
    for batch in batches:
        keys = [f"{cls.__module__}.{cls.__qualname__}" for cls, _tests in batch]
        batch_specs.append(",".join(keys))

    # Clone databases
    t_clone = time.time()
    clone_names = clone_databases(db_name, actual_workers)
    _logger.info("Cloning took %.1fs", time.time() - t_clone)

    # Spawn workers
    t_run = time.time()
    workers = spawn_workers(clone_names, batch_specs)

    # Wait and collect
    worker_results = wait_for_workers(workers)
    elapsed = time.time() - t_run

    # Print worker output to master stdout so `| tee` captures everything
    for wr in worker_results:
        idx = wr["index"]
        output = wr["output"]
        if output.strip():
            sys.stdout.write(f"\n{'=' * 70}\n")
            sys.stdout.write(f"=== Parallel Worker {idx} Output ===\n")
            sys.stdout.write(f"{'=' * 70}\n")
            sys.stdout.write(output)
            sys.stdout.write("\n")
            sys.stdout.flush()

    # Aggregate results
    aggregated = OdooTestResult(global_report=global_report)
    for wr in worker_results:
        tr = wr["test_result"]
        if tr:
            aggregated.failures_count += tr["failures_count"]
            aggregated.errors_count += tr["errors_count"]
            aggregated.testsRun += tr["testsRun"]
            aggregated.skipped += tr["skipped"]
        elif wr["returncode"] != 0:
            # Worker crashed without writing results — count as error
            aggregated.errors_count += 1
            _logger.error(
                "Worker %d crashed (exit code %d) without writing results",
                wr["index"],
                wr["returncode"],
            )

    _logger.info(
        "Parallel run complete in %.1fs: %s",
        elapsed,
        aggregated,
    )

    # Merge per-class durations from all workers into the persistent stats
    # file so the next run can use LPT balancing
    all_durations = {}
    for wr in worker_results:
        tr = wr.get("test_result")
        if tr and "class_durations" in tr:
            all_durations.update(tr["class_durations"])
    if all_durations:
        save_stats(all_durations)

    # Keep clones for reuse on the next run (default). Stale clones are
    # cleaned up at the start of the next run inside clone_databases().
    if not config.reuse_clones():
        drop_databases(clone_names)

    return aggregated


# ---------------------------------------------------------------------------
# The patched run_suite
# ---------------------------------------------------------------------------


def _patched_run_suite(suite, global_report=None):
    """
    Drop-in replacement for odoo.tests.loader.run_suite.

    Three paths:
    1. Worker mode (ODOO_PARALLEL_BATCH set): filter and run assigned tests
    2. Post-install phase with multiple classes: parallelize
    3. Everything else: run sequentially with the original function
    """
    # Path 1: worker subprocess — filter to assigned batch
    batch = os.environ.get("ODOO_PARALLEL_BATCH")
    if batch:
        return _worker_run(suite, batch, global_report)

    # Path 2: master, post-install, conditions met — parallelize
    if _is_post_install_phase() and _should_parallelize(suite):
        try:
            return _parallel_run(suite, global_report)
        except Exception as exc:
            _logger.info(
                "Parallel execution unavailable, running sequentially (%s)", exc
            )

    # Path 3: sequential (at-install, single class, or fallback)
    return _original_run_suite(suite, global_report=global_report)


# ---------------------------------------------------------------------------
# Patch application (called from __init__.py)
# ---------------------------------------------------------------------------

def _apply():
    global _original_run_suite

    from odoo.tests import loader

    _original_run_suite = loader.run_suite
    loader.run_suite = _patched_run_suite
    _logger.info(
        "Parallel test runner patch applied (mode: %s, workers: %d)",
        config.get_parallel_mode(),
        config.get_worker_count(),
    )


_apply()
