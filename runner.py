"""
Worker subprocess management for parallel test execution.

Each worker is a full odoo-bin process targeting a cloned database.
The ODOO_PARALLEL_BATCH env var tells the worker which test classes
to run (our patch in the worker filters the suite accordingly).
Results are communicated back via a JSON file per worker.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading

_logger = logging.getLogger(__name__)

# Workers that exceed this timeout are killed
WORKER_TIMEOUT = 600  # 10 minutes

# Shared lock so lines from concurrent workers don't interleave on stdout
_stdout_lock = threading.Lock()


def _stream_worker_output(proc, out_fh, prefix):
    """
    Read a worker's stdout line by line, writing each line to both the log
    file and the master console so progress is visible in real time.
    Runs in a daemon thread; exits when the worker process closes its stdout.
    """
    for line in proc.stdout:
        out_fh.write(line)
        with _stdout_lock:
            sys.stdout.write(prefix + line)
            sys.stdout.flush()
    out_fh.flush()


def _build_worker_command(clone_db, port):
    """
    Build the odoo-bin command for a worker subprocess.

    Reconstructs the command from the current Odoo config, replacing the
    database name and port, and stripping -i/-u flags (the clone already
    has all modules installed).
    """
    from odoo import tools

    odoo_bin = os.path.abspath(sys.argv[0])

    # addons_path is stored as a list internally; join with commas for CLI
    addons_path = tools.config["addons_path"]
    if isinstance(addons_path, (list, tuple)):
        addons_path = ",".join(addons_path)

    cmd = [
        sys.executable,
        odoo_bin,
        "--stop-after-init",
        f"--addons-path={addons_path}",
        "--test-enable",
        "-d",
        clone_db,
        "--max-cron-threads",
        "0",
        "--limit-time-real",
        "0",
        "--without-demo=True",
        "--http-interface",
        "127.0.0.1",
        "-p",
        str(port),
        "--log-level",
        "test",
    ]

    if tools.config.get("test_tags"):
        cmd.append(f"--test-tags={tools.config['test_tags']}")
    if tools.config.get("db_user"):
        cmd.extend(["-r", tools.config["db_user"]])
    if tools.config.get("db_password"):
        cmd.extend(["-w", tools.config["db_password"]])
    if tools.config.get("db_host"):
        cmd.extend(["--db_host", tools.config["db_host"]])
    if tools.config.get("db_port"):
        cmd.extend(["--db_port", str(tools.config["db_port"])])

    return cmd


def spawn_workers(clone_names, batch_specs):
    """
    Spawn worker subprocesses, one per clone database.

    Each worker gets:
    - ODOO_PARALLEL_BATCH: comma-separated list of qualified class names
    - ODOO_PARALLEL_RESULT: path to write JSON test results
    - ODOO_TEST_PARALLEL=never: prevent recursive parallelization

    Returns list of (process, output_path, result_path, worker_index) tuples.
    """
    tmpdir = tempfile.mkdtemp(prefix="odoo_parallel_tests_")
    _logger.info("Worker output directory: %s", tmpdir)
    base_port = 9000
    workers = []

    for i, (clone_db, batch_spec) in enumerate(zip(clone_names, batch_specs)):
        output_path = os.path.join(tmpdir, f"worker_{i}.log")
        result_path = os.path.join(tmpdir, f"worker_{i}.json")

        cmd = _build_worker_command(clone_db, base_port + i)

        env = os.environ.copy()
        env["ODOO_PARALLEL_BATCH"] = batch_spec
        env["ODOO_PARALLEL_RESULT"] = result_path
        env["ODOO_TEST_PARALLEL"] = "never"

        class_count = len(batch_spec.split(","))
        _logger.info(
            "Starting worker %d on %s (%d classes)", i, clone_db, class_count
        )
        _logger.debug("Worker %d command: %s", i, " ".join(cmd))

        out_fh = open(output_path, "w")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        # Stream each worker's output to both its log file and the console,
        # prefixed with the worker index so interleaved lines stay readable.
        thread = threading.Thread(
            target=_stream_worker_output,
            args=(proc, out_fh, f"[W{i}] "),
            daemon=True,
        )
        thread.start()

        workers.append((proc, output_path, result_path, i, out_fh, thread))

    return workers


def wait_for_workers(workers):
    """
    Wait for all worker processes to finish.

    Returns a list of dicts with keys:
      index, returncode, output, test_result (dict or None)
    """
    results = []

    for proc, output_path, result_path, idx, out_fh, thread in workers:
        try:
            proc.wait(timeout=WORKER_TIMEOUT)
        except subprocess.TimeoutExpired:
            _logger.error(
                "Worker %d timed out after %ds — killing", idx, WORKER_TIMEOUT
            )
            proc.kill()
            proc.wait()
        finally:
            # Wait for the streaming thread to drain all buffered output before
            # closing the file handle; otherwise the last lines can be lost.
            thread.join()
            out_fh.close()

        # Read captured output
        output = ""
        if os.path.exists(output_path):
            with open(output_path) as f:
                output = f.read()

        # Read structured result
        test_result = None
        if os.path.exists(result_path):
            with open(result_path) as f:
                try:
                    test_result = json.load(f)
                except json.JSONDecodeError:
                    _logger.error("Worker %d produced invalid result JSON", idx)

        returncode = proc.returncode
        _logger.info("Worker %d finished (exit code: %d)", idx, returncode)

        results.append(
            {
                "index": idx,
                "returncode": returncode,
                "output": output,
                "test_result": test_result,
            }
        )

    return results
