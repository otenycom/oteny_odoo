"""
Database cloning utilities for parallel test execution.

Uses PostgreSQL's createdb -T (template clone) which is fast because
it does a file-level copy. Requires no active connections on the
template database during cloning.

Clone reuse: after a parallel run, clones are kept. On the next run three
fingerprints detect whether the base DB has changed:
1. Schema fingerprint — md5 of all public table columns + types
2. XML-ID fingerprint — md5 of ir_model_data rows (module.name=model:res_id)
3. Module-version fingerprint — md5 of ir_module_module name=latest_version
If all three match AND the right number of clones still exist, cloning is
skipped entirely (~0s vs ~9s). The XML-ID fingerprint catches the common
case where noupdate=1 data records are added without schema changes. The
module-version fingerprint catches a value-only migration: the schema and
XML-ID set stay the same, but latest_version moves, so clones refresh.

Filestore: a clone's ir_attachment rows point at files under the BASE DB's
filestore (asset bundles, install-time fixture PDFs, ...), but Odoo resolves
a database's filestore by database name, so a fresh clone used to start with
an empty filestore. A browser test (HttpCase.start_tour) then never booted
its web client, and any test rendering an installed fixture raised
FileNotFoundError. Every fresh clone now gets a replica of the base
filestore, hardlinked (no bytes copied; a copy is the fallback), and the
replica is removed with the clone. Hardlinks are safe against Odoo's
end-of-run filestore GC: unlinking a worker's link never touches the base.
"""

import json
import logging
import os
import shutil
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


def _get_module_version_fingerprint(db_name):
    """
    Compute an md5 hash of installed module versions.

    A migration that only rewrites a field value on an existing record
    changes neither the schema nor the XML-ID set. It does bump
    ir_module_module.latest_version after -u, so this hash moves and
    stale worker clones are discarded.
    """
    env = _get_pg_env()
    args = _get_pg_args()
    sql = (
        "SELECT md5(string_agg("
        "name || '=' || COALESCE(latest_version, ''), "
        "',' ORDER BY name)) "
        "FROM ir_module_module "
        "WHERE state = 'installed'"
    )
    cmd = ["psql", "-d", db_name] + args + ["-t", "-A", "-c", sql]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _reuse_key_matches(
    state,
    *,
    base_db,
    fingerprint,
    xmlid_fingerprint,
    version_fingerprint,
    count,
    clone_names,
):
    """True when saved clone state matches the current schema, XML-ID, and version key."""
    if not fingerprint or not xmlid_fingerprint or not version_fingerprint:
        return False
    return (
        state.get("base_db") == base_db
        and state.get("fingerprint") == fingerprint
        and state.get("xmlid_fingerprint") == xmlid_fingerprint
        and state.get("version_fingerprint") == version_fingerprint
        and state.get("worker_count") == count
        and state.get("clone_names") == clone_names
    )


def _reuse_miss_reasons(state, fingerprint, xmlid_fingerprint, version_fingerprint, count):
    """Human-readable reasons the saved clone state does not match the current key."""
    reasons = []
    if state.get("fingerprint") != fingerprint:
        reasons.append("schema changed")
    if state.get("xmlid_fingerprint") != xmlid_fingerprint:
        reasons.append("XML IDs changed")
    if state.get("version_fingerprint") != version_fingerprint:
        reasons.append("module versions changed")
    if state.get("worker_count") != count:
        reasons.append("worker count changed")
    return reasons


def _load_clone_state():
    """Load the clone state file. Returns dict or empty dict on any error."""
    if not os.path.exists(CLONE_STATE_PATH):
        return {}
    try:
        with open(CLONE_STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_clone_state(
    base_db, fingerprint, xmlid_fingerprint, version_fingerprint, clone_names
):
    """Persist the clone state so the next run can attempt reuse."""
    try:
        with open(CLONE_STATE_PATH, "w") as f:
            json.dump(
                {
                    "base_db": base_db,
                    "fingerprint": fingerprint,
                    "xmlid_fingerprint": xmlid_fingerprint,
                    "version_fingerprint": version_fingerprint,
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
# Filestore replication
# ---------------------------------------------------------------------------

# Odoo's filestore GC keeps its to-delete markers here; a clone starts clean.
FILESTORE_SKIP_DIRS = ("checklist",)
# Written into a replica once it is complete, so a reused clone from before
# the replication existed (an empty or partial filestore) is topped up.
FILESTORE_MARKER = ".hh-filestore-replica"


def _filestore_dir(db_name):
    """Where Odoo keeps this database's attachments (data_dir/filestore/<db>)."""
    from odoo import tools

    return tools.config.filestore(db_name)


def replicate_filestore(base_dir, clone_dir, replace=True):
    """Give a clone the base database's filestore.

    Every file is hardlinked (metadata only, no bytes copied); a file that
    cannot be linked (another volume, a permission quirk) is copied instead.
    With ``replace`` (a fresh clone) a stale ``clone_dir`` is replaced.
    Without it (a reused clone that lacks the marker) the base is merged in
    and the clone's own files are kept. A missing ``base_dir`` is a no-op.

    Returns ``(files, linked, copied)``; ``files`` counts the base files
    handled, including those the merge left as they were.
    """
    if not os.path.isdir(base_dir):
        return 0, 0, 0
    if replace and os.path.lexists(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)
    files = linked = copied = 0
    for root, dirs, names in os.walk(base_dir):
        rel = os.path.relpath(root, base_dir)
        if rel == ".":
            rel = ""
            dirs[:] = [d for d in dirs if d not in FILESTORE_SKIP_DIRS]
            names = [n for n in names if n != FILESTORE_MARKER]
        target_root = os.path.join(clone_dir, rel) if rel else clone_dir
        os.makedirs(target_root, exist_ok=True)
        for name in names:
            src = os.path.join(root, name)
            dst = os.path.join(target_root, name)
            files += 1
            if os.path.lexists(dst):
                continue
            try:
                os.link(src, dst)
                linked += 1
            except OSError:
                shutil.copy2(src, dst)
                copied += 1
    with open(os.path.join(clone_dir, FILESTORE_MARKER), "w") as marker:
        marker.write(base_dir + "\n")
    return files, linked, copied


def has_filestore_replica(clone_dir):
    """True once ``replicate_filestore`` completed for this clone."""
    return os.path.isfile(os.path.join(clone_dir, FILESTORE_MARKER))


def remove_filestore(clone_dir):
    """Remove a clone's filestore replica; a missing directory is fine."""
    if os.path.lexists(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)


def _replicate_filestore_for(base_db, clone_name, replace=True):
    files, linked, copied = replicate_filestore(
        _filestore_dir(base_db), _filestore_dir(clone_name), replace=replace
    )
    _logger.info(
        "Filestore for %s: %d base files (%d hardlinked, %d copied)",
        clone_name, files, linked, copied,
    )


# ---------------------------------------------------------------------------
# Clone / reuse
# ---------------------------------------------------------------------------


def clone_databases(base_db, count):
    """
    Provide N worker databases, either by reusing existing clones (when the
    base DB schema, XML IDs, and module versions have not changed and the
    right number of clones still exist) or by creating fresh clones via
    createdb -T.

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
    # Schema, XML-ID, and module-version fingerprints must all match.
    # The version check catches a value-only migration: same columns and
    # same ir_model_data rows, but latest_version moved after -u.
    if config.reuse_clones():
        fingerprint = _get_db_fingerprint(base_db)
        xmlid_fingerprint = _get_xmlid_fingerprint(base_db)
        version_fingerprint = _get_module_version_fingerprint(base_db)
        state = _load_clone_state()
        if _reuse_key_matches(
            state,
            base_db=base_db,
            fingerprint=fingerprint,
            xmlid_fingerprint=xmlid_fingerprint,
            version_fingerprint=version_fingerprint,
            count=count,
            clone_names=clone_names,
        ) and _clones_exist(clone_names):
            _logger.info(
                "Reusing %d existing clone databases "
                "(schema, XML IDs, and module versions unchanged)",
                count,
            )
            # A reused clone keeps its own filestore between runs. A clone
            # from before replication existed, or a replica removed by hand,
            # is topped up from the base without touching the clone's own files.
            for clone_name in clone_names:
                if not has_filestore_replica(_filestore_dir(clone_name)):
                    _replicate_filestore_for(base_db, clone_name, replace=False)
            return clone_names
        if state:
            reasons = _reuse_miss_reasons(
                state, fingerprint, xmlid_fingerprint, version_fingerprint, count
            )
            _logger.info(
                "Clone cache miss — %s",
                ", ".join(reasons) if reasons else "creating fresh clones",
            )
        else:
            _logger.info("Clone cache miss — no prior state")
    else:
        fingerprint = None
        xmlid_fingerprint = None
        version_fingerprint = None

    # Need fresh clones — close connections and clone
    _fresh_clone(base_db, clone_names)

    # Save state for future reuse
    if config.reuse_clones():
        if not fingerprint:
            fingerprint = _get_db_fingerprint(base_db)
        if not xmlid_fingerprint:
            xmlid_fingerprint = _get_xmlid_fingerprint(base_db)
        if not version_fingerprint:
            version_fingerprint = _get_module_version_fingerprint(base_db)
        if fingerprint and xmlid_fingerprint and version_fingerprint:
            _save_clone_state(
                base_db,
                fingerprint,
                xmlid_fingerprint,
                version_fingerprint,
                clone_names,
            )

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
            _replicate_filestore_for(base_db, clone_name)

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
            remove_filestore(_filestore_dir(name))
