"""Drop orphan rows left by a restore, so the foreign keys they block can be re-added.

Background
----------
`oteny_audit_log_ref.audit_log_id` references `oteny_audit_log(id)` ON DELETE CASCADE, so an
orphan ref is impossible while that foreign key exists. It becomes possible in exactly one
window: a restore. `pg_restore` loads the rows first and re-adds the constraints last, so for
several minutes the table has data and no foreign key. Anything that deletes from
`oteny_audit_log` in that window orphans its refs, and the constraint can then never be
re-added — `ALTER TABLE ... ADD FOREIGN KEY` fails, the registry fails to load, and every
later upgrade of the database fails with it.

That is not hypothetical. On 2026-08-25, restoring `cr.zip` into `crmain` with a
`cr-cron-enabled` server still running, cron 15 ("Audit Log: Cleanup Old Records") fired
against the half-loaded database and left **78,297** orphan rows. The required `-i` / `-u`
then failed on:

    ALTER TABLE "oteny_audit_log_ref" ADD FOREIGN KEY ("audit_log_id")
        REFERENCES "oteny_audit_log"("id") ON DELETE cascade
    ERROR: insert or update on table "oteny_audit_log_ref" violates foreign key constraint

The same window damages more than one table, because more than one background job runs. The
full set measured on that database, after the failed restore:

    oteny_audit_log_ref.audit_log_id          78,297   (Audit Log: Cleanup Old Records)
    discuss_channel_member.channel_id             64   (AI-chat channel autovacuum)
    documents_access.document_id                   3
    discuss_channel_member.fetched_message_id      1
    discuss_channel_member.seen_message_id         1

`riverdeploy/crewradar_db_restore.py::stop_odoo_servers` closes that window going forward.
This script is the other half: it repairs a database that already fell into it, so the
recovery is an upgrade rather than a second full restore.

Why these tables live here, and why 19.0.1.329 is not enough
------------------------------------------------------------
`migrations/19.0.1.329/pre-migrate.py` already repairs orphan `discuss_channel_member` rows,
and its docstring makes the case for hosting a cross-cutting repair in `oteny_audit`: the
module loads early (~47/166) and depends on `mail`, so its pre-migration is in time for the
foreign keys that later modules pull in. That argument still holds and is why this script
sits here too.

What it cannot do is run again. A migration folder only executes for a database whose
installed version is below it, so 19.0.1.329 is unreachable on every database past 329 —
`crmain` was at 19.0.1.494 — while the condition it repairs recurs on every restore. This
script is the re-armed version at the current ceiling.

Why pre-migrate
---------------
Odoo adds a module's foreign keys during that module's `init_models`, and a pre-migration
runs immediately before it. This is the earliest point at which the rows can be removed and
still be in time. A post-migration would run after the `ALTER TABLE` that fails.

Deleting is correct, not lossy: a ref whose audit log row is gone points at nothing, and the
cascade the constraint declares is what should have removed it.
"""

import logging

_logger = logging.getLogger(__name__)

# (child table, child column, parent table, parent column). Every entry is a cascade or
# set-null reference, so a row whose parent is gone points at nothing and should already have
# been removed. Add a row here when a restore turns up another one — the diagnostic that
# produced this list is in the restore reference under "A running crmain server wrecks the
# restore".
_CASCADE_REFERENCES = (
    ("oteny_audit_log_ref", "audit_log_id", "oteny_audit_log", "id"),
    ("discuss_channel_member", "channel_id", "discuss_channel", "id"),
    ("discuss_channel_member", "fetched_message_id", "mail_message", "id"),
    ("discuss_channel_member", "seen_message_id", "mail_message", "id"),
    ("documents_access", "document_id", "documents_document", "id"),
)


def _table_exists(cr, table):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table,),
    )
    return cr.fetchone()[0]


def migrate(cr, version):
    total = 0
    for child, column, parent, parent_column in _CASCADE_REFERENCES:
        if not (_table_exists(cr, child) and _table_exists(cr, parent)):
            continue
        cr.execute(
            f"""
            DELETE FROM {child} c
            WHERE c.{column} IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM {parent} p WHERE p.{parent_column} = c.{column}
              )
            """
        )
        if cr.rowcount:
            total += cr.rowcount
            _logger.warning(
                "pre-migrate 19.0.1.519: deleted %d orphan %s rows whose %s.%s no longer "
                "exists",
                cr.rowcount, child, parent, parent_column,
            )

    if total:
        _logger.warning(
            "pre-migrate 19.0.1.519: repaired %d orphan rows in total. The ON DELETE cascade "
            "should have removed them; they survive only when parents are deleted while the "
            "foreign key is absent, which is the window a database restore opens.",
            total,
        )
