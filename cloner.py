"""
Database cloning utilities for parallel test execution.

Uses PostgreSQL's createdb -T (template clone) which is fast because
it does a file-level copy. Requires no active connections on the
template database during cloning.

Clone reuse: after a parallel run, clones are kept. On the next run two
fingerprints detect whether the base DB has changed:
1. Schema fingerprint — md5 of all public table columns + types
2. XML-ID fingerprint — md5 of ir_model_data rows (module.name=model:res_id)
If both match AND the right number of clones still exist, cloning is
skipped entirely (~0s vs ~9s). The XML-ID fingerprint catches the common
case where noupdate=1 data records are added without schema changes.
"""

import json
import logging
import os
import subprocess

_logger = logging.getLogger(__name__)

CLONE_STATE_PATH = "/tmp/odoo_parallel_test_clones.json"


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------


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


def _can_createdb():
    """
    Pre-flight check: verify that createdb will work by testing the
    pg_catalog.set_config permission that createdb uses internally.
    On managed PostgreSQL hosts (e.g. Odoo.sh) this permission is
    sometimes revoked, causing createdb to fail with zombie processes.
    """
    env = _get_pg_env()
    args = _get_pg_args()
    sql = "SELECT pg_catalog.set_config('search_path', '', false);"
    cmd = ["psql", "-d", "postgres"] + args + ["-t", "-A", "-c", sql]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        _logger.info(
            "Parallel cloning unavailable: pg_catalog.set_config permission denied"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Schema fingerprint & clone state persistence
# ---------------------------------------------------------------------------


def _get_db_fingerprint(db_name):
    """
    Compute an md5 hash of the database's public schema (all table columns
    and their types). Changes whenever -u adds, removes, or changes any
    column — even without a manifest version bump.
    """
    env = _get_pg_env()
    args = _get_pg_args()
    sql = (
        "SELECT md5(string_agg("
        "schemaname || '.' || tablename || ':' || attname || '=' || typname, "
        "',' ORDER BY schemaname, tablename, attname)) "
        "FROM ("
        "  SELECT s.nspname AS schemaname, c.relname AS tablename, "
        "         a.attname, t.typname "
        "  FROM pg_attribute a "
        "  JOIN pg_class c ON a.attrelid = c.oid "
        "  JOIN pg_namespace s ON c.relnamespace = s.oid "
        "  JOIN pg_type t ON a.atttypid = t.oid "
        "  WHERE s.nspname = 'public' AND c.relkind = 'r' "
        "    AND a.attnum > 0 AND NOT a.attisdropped"
        ") sub"
    )
    cmd = ["psql", "-d", db_name] + args + ["-t", "-A", "-c", sql]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _get_xmlid_fingerprint(db_name):
    """
    Compute an md5 hash of ir_model_data rows (XML IDs). Detects when
    -u or -i adds/removes/changes data records without altering the schema.

    This catches the common case where noupdate=1 records are added to XML
    data files: the schema fingerprint stays the same (no new columns), but
    the clones are stale because they lack the new data records.
    """
    env = _get_pg_env()
    args = _get_pg_args()
    sql = (
        "SELECT md5(string_agg("
        "module || '.' || name || '=' || model || ':' || res_id::text, "
        "',' ORDER BY module, name)) "
        "FROM ir_model_data"
    )
    cmd = ["psql", "-d", db_name] + args + ["-t", "-A", "-c", sql]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _load_clone_state():
    """Load the clone state file. Returns dict or empty dict on any error."""
    if not os.path.exists(CLONE_STATE_PATH):
        return {}
    try:
        with open(CLONE_STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_clone_state(base_db, fingerprint, xmlid_fingerprint, clone_names):
    """Persist the clone state so the next run can attempt reuse."""
    try:
        with open(CLONE_STATE_PATH, "w") as f:
            json.dump(
                {
                    "base_db": base_db,
                    "fingerprint": fingerprint,
                    "xmlid_fingerprint": xmlid_fingerprint,
                    "clone_names": clone_names,
                    "worker_count": len(clone_names),
                },
                f,
            )
    except OSError as exc:
        _logger.warning("Could not save clone state: %s", exc)


def _clones_exist(clone_names):
    """Verify all clone databases exist in PostgreSQL."""
    env = _get_pg_env()
    args = _get_pg_args()
    cmd = ["psql", "-d", "postgres"] + args + ["-t", "-A", "-c",
           "SELECT datname FROM pg_database"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    existing = set(result.stdout.strip().splitlines())
    return all(name in existing for name in clone_names)


# ---------------------------------------------------------------------------
# Clone / reuse
# ---------------------------------------------------------------------------


def clone_databases(base_db, count):
    """
    Provide N worker databases, either by reusing existing clones (when the
    base DB schema has not changed and the right number of clones still exist)
    or by creating fresh clones via createdb -T.

    Returns list of clone db names.
    Raises RuntimeError if cloning is not possible (e.g. permission issues).
    """
    from . import config

    prefix = config.get_clone_prefix().replace("{db}", base_db)
    clone_names = [f"{prefix}{i}" for i in range(count)]

    # Pre-flight: verify we have the permissions that createdb needs.
    # Avoids spawning N doomed processes that become zombies on failure.
    if not _can_createdb():
        raise RuntimeError(
            "Database cloning unavailable: insufficient PostgreSQL permissions"
        )

    # Check if we can reuse clones from the previous run.
    # Both the schema fingerprint (column definitions) and the XML-ID
    # fingerprint (ir_model_data rows) must match. The XML-ID check
    # catches additions of noupdate=1 data records that don't alter
    # the schema but do change the database content.
    if config.reuse_clones():
        fingerprint = _get_db_fingerprint(base_db)
        xmlid_fingerprint = _get_xmlid_fingerprint(base_db)
        state = _load_clone_state()
        if (
            fingerprint
            and xmlid_fingerprint
            and state.get("base_db") == base_db
            and state.get("fingerprint") == fingerprint
            and state.get("xmlid_fingerprint") == xmlid_fingerprint
            and state.get("worker_count") == count
            and state.get("clone_names") == clone_names
            and _clones_exist(clone_names)
        ):
            _logger.info("Reusing %d existing clone databases (schema and XML IDs unchanged)", count)
            return clone_names
        if state:
            reasons = []
            if state.get("fingerprint") != fingerprint:
                reasons.append("schema changed")
            if state.get("xmlid_fingerprint") != xmlid_fingerprint:
                reasons.append("XML IDs changed")
            if state.get("worker_count") != count:
                reasons.append("worker count changed")
            _logger.info("Clone cache miss — %s", ", ".join(reasons) if reasons else "creating fresh clones")
        else:
            _logger.info("Clone cache miss — no prior state")
    else:
        fingerprint = None
        xmlid_fingerprint = None

    # Need fresh clones — close connections and clone
    _fresh_clone(base_db, clone_names)

    # Save state for future reuse
    if config.reuse_clones():
        if not fingerprint:
            fingerprint = _get_db_fingerprint(base_db)
        if not xmlid_fingerprint:
            xmlid_fingerprint = _get_xmlid_fingerprint(base_db)
        if fingerprint:
            _save_clone_state(base_db, fingerprint, xmlid_fingerprint, clone_names)

    return clone_names


def _fresh_clone(base_db, clone_names):
    """
    Drop any existing clones and create fresh ones from the base database.

    Closes Odoo's connection pool first so createdb -T can acquire exclusive
    access to the template. Launches all operations concurrently.
    """
    import odoo.sql_db

    odoo.sql_db.close_db(base_db)
    _terminate_connections(base_db)

    env = _get_pg_env()
    pg_args = _get_pg_args()

    # Phase 1: drop stale clones in parallel
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

    # Collect results; on failure, wait for ALL remaining processes before
    # raising to prevent zombie processes lingering until the test harness
    # detects and warns about them.
    created = []
    first_error = None
    for clone_name, proc in clone_procs:
        _stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            _logger.info("Cannot clone %s -> %s: %s", base_db, clone_name, err)
            if first_error is None:
                first_error = err
        else:
            created.append(clone_name)
            _logger.info("Cloned database: %s", clone_name)

    if first_error is not None:
        drop_databases(created)
        raise RuntimeError(f"Database cloning failed: {first_error}")


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
