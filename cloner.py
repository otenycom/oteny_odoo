"""
Database cloning utilities for parallel test execution.

Uses PostgreSQL's createdb -T (template clone) which is fast because
it does a file-level copy. Requires no active connections on the
template database during cloning.

Cloning and cleanup run as concurrent subprocesses to overlap the
per-process overhead. PostgreSQL serializes createdb -T against the
same template via locks, but we still save on subprocess startup,
dropdb cleanup, and especially the drop phase at the end.
"""

import logging
import os
import subprocess

_logger = logging.getLogger(__name__)


def _get_pg_env():
    """Build environment dict for PostgreSQL CLI commands (password via PGPASSWORD)."""
    from odoo import tools

    env = os.environ.copy()
    if tools.config["db_password"]:
        env["PGPASSWORD"] = tools.config["db_password"]
    return env


def _get_pg_args():
    """Build common PostgreSQL CLI arguments for user/host/port."""
    from odoo import tools

    args = []
    if tools.config["db_user"]:
        args.extend(["-U", tools.config["db_user"]])
    if tools.config["db_host"]:
        args.extend(["-h", tools.config["db_host"]])
    if tools.config.get("db_port"):
        args.extend(["-p", str(tools.config["db_port"])])
    return args


def _terminate_connections(db_name):
    """Terminate all PostgreSQL connections to a database via psql."""
    env = _get_pg_env()
    args = _get_pg_args()
    sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"
    )
    cmd = ["psql", "-d", "postgres"] + args + ["-c", sql]
    subprocess.run(cmd, env=env, capture_output=True)


def clone_databases(base_db, count):
    """
    Clone the base test database into N worker databases.

    Closes Odoo's connection pool first so createdb -T can acquire
    exclusive access to the template. Launches all clone operations
    concurrently — PostgreSQL serializes the template lock internally,
    but we overlap subprocess startup and the dropdb cleanup.
    Returns list of clone db names.
    """
    from . import config

    prefix = config.get_clone_prefix().replace("{db}", base_db)
    clone_names = [f"{prefix}{i}" for i in range(count)]

    # Close Odoo's connections to allow createdb -T to access the template
    import odoo.sql_db

    odoo.sql_db.close_db(base_db)

    # Belt-and-suspenders: also terminate via psql in case other processes
    # (e.g. pgAdmin, monitoring) hold connections
    _terminate_connections(base_db)

    env = _get_pg_env()
    pg_args = _get_pg_args()

    # Phase 1: drop leftover clones in parallel (fully independent)
    drop_procs = []
    for clone_name in clone_names:
        proc = subprocess.Popen(
            ["dropdb", "--if-exists"] + pg_args + [clone_name],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        drop_procs.append(proc)
    for proc in drop_procs:
        proc.wait()

    # Phase 2: clone in parallel — PostgreSQL serializes the template lock
    # but we overlap subprocess startup and handshake overhead
    clone_procs = []
    for clone_name in clone_names:
        proc = subprocess.Popen(
            ["createdb"] + pg_args + ["-T", base_db, clone_name],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        clone_procs.append((clone_name, proc))

    # Collect results; abort on first failure
    created = []
    for clone_name, proc in clone_procs:
        _stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            _logger.error("Failed to clone %s -> %s: %s", base_db, clone_name, err)
            drop_databases(created)
            raise RuntimeError(f"Database cloning failed: {err}")
        created.append(clone_name)
        _logger.info("Cloned database: %s", clone_name)

    return clone_names


def drop_databases(clone_names):
    """Drop cloned worker databases concurrently, terminating connections first."""
    env = _get_pg_env()
    pg_args = _get_pg_args()

    # Terminate connections to all clones in parallel
    term_procs = []
    for name in clone_names:
        sql = (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{name}' AND pid <> pg_backend_pid();"
        )
        cmd = ["psql", "-d", "postgres"] + pg_args + ["-c", sql]
        proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        term_procs.append(proc)
    for proc in term_procs:
        proc.wait()

    # Drop all clones in parallel (independent databases, no lock contention)
    drop_procs = []
    for name in clone_names:
        proc = subprocess.Popen(
            ["dropdb", "--if-exists"] + pg_args + [name],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        drop_procs.append((name, proc))

    for name, proc in drop_procs:
        _stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            _logger.warning(
                "Failed to drop database %s: %s", name, stderr.decode().strip()
            )
        else:
            _logger.debug("Dropped database: %s", name)
