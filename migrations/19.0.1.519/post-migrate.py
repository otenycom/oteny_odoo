"""Scrub credentials already written into the audit log in cleartext.

Background
----------
`oteny_audit` patches the ORM and copies every stored, non-readonly field value into
`oteny_audit_log`. Until 19.0.1.519 it made no exception for a credential. Two things
made that a live exposure rather than a theoretical one:

1. `security/ir.model.access.csv` grants `base.group_user` read on `oteny.audit.log`,
   `oteny.audit.log.ref` and `oteny.audit.log.aggregated`, with no record rule and no
   `groups=` on the Audit menu. So every internal user can read and value-search the
   whole history.
2. The create/unlink snapshot is built from a raw `SELECT` on the table, which bypasses
   the field-level `groups='base.group_system'` that core Odoo puts on `ir.mail_server.
   smtp_pass` and `iap.account.account_token`.

Measured on the `test1` database on 2026-08-25: cleartext values for `ai.anthropic_key`,
`ai.google_key`, `iap_vies.client_token`, `oteny.broker_token`,
`oteny.broker_token_live_watch` and `oteny.broker_token_replay_view`, going back to
2026-03-02; plus 2,081 `access_token`, 852 `document_token`, 53 `bot_claim_token`,
30 `login_dance_token` and 11 `refresh_token` rows across other models.

19.0.1.519 stops NEW rows carrying a value (`base_patch._maybe_redact`). This migration
deals with the rows already written.

What it does
------------
Redacts, never deletes. Deleting the rows would destroy the audit trail the module exists
to keep, and would break `_recover_unlinked_display_name`, which reads a historical
`record_display_name` off an older row. The row, its timestamp, its user and its field
name all survive; only the value becomes the same placeholder the runtime now writes.

Three passes, because a value lives in two different shapes:

* flat columns (`old_value` / `new_value` / `*_display_name`) carry UPDATE rows;
* the `snapshot` jsonb carries every INSERT and DELETE row.

A scrub that touches only the flat columns leaves every insert and delete untouched — and
for a rotated-out parameter the DELETE tombstone is exactly the row that preserved the old
secret.

Not touched, deliberately
-------------------------
`oteny_audit_log_ref.target_display_name` / `parent_display_name` copy
`record_display_name`, which is the RECORD's name, not a field value. No model in this
database has a credential as its `_rec_name`; `ir.config_parameter._rec_name` is `key`,
which must stay readable both for the auditor and for
`base_patch._check_and_disable_on_restore`.

This does not un-expose anything. Any credential listed above must still be rotated.
"""

import logging

from odoo.addons.oteny_audit.models.base_patch import AUDIT_REDACTED, _is_secret_field_name
from odoo.addons.oteny_audit.models.ir_config_parameter_override import (
    is_secret_param_key,
    is_secret_param_value,
)

_logger = logging.getLogger(__name__)

def _predicate(sql, predicate):
    """Substitute the WHERE predicate into a scrub template.

    A plain `str.format` cannot be used: the snapshot SQL contains a literal `'{}'::jsonb`,
    which `format` reads as a positional placeholder and rejects.
    """
    return sql.replace("{predicate}", predicate)


_REDACT_FLAT_SQL = """
    UPDATE oteny_audit_log
    SET old_value = CASE WHEN COALESCE(old_value, '') <> '' THEN %(placeholder)s ELSE old_value END,
        new_value = CASE WHEN COALESCE(new_value, '') <> '' THEN %(placeholder)s ELSE new_value END,
        old_value_display_name = CASE WHEN COALESCE(old_value_display_name, '') <> ''
                                      THEN %(placeholder)s ELSE old_value_display_name END,
        new_value_display_name = CASE WHEN COALESCE(new_value_display_name, '') <> ''
                                      THEN %(placeholder)s ELSE new_value_display_name END
    WHERE {predicate}
      AND (COALESCE(old_value, '') NOT IN ('', %(placeholder)s)
           OR COALESCE(new_value, '') NOT IN ('', %(placeholder)s)
           OR COALESCE(old_value_display_name, '') NOT IN ('', %(placeholder)s)
           OR COALESCE(new_value_display_name, '') NOT IN ('', %(placeholder)s))
"""

_REDACT_SNAPSHOT_SQL = """
    UPDATE oteny_audit_log
    SET snapshot = jsonb_set(
            jsonb_set(snapshot, ARRAY[%(key)s, 'raw'], to_jsonb(%(placeholder)s::text), false),
            ARRAY[%(key)s, 'display'], to_jsonb(%(placeholder)s::text), false)
    WHERE field_name = '__snapshot__'
      AND snapshot @> jsonb_build_object(%(key)s, '{}'::jsonb)
      AND {predicate}
      -- An entry is always {raw, display, label}. Requiring an object keeps the statement
      -- idempotent: jsonb_set into a scalar is a no-op, so without this a malformed entry
      -- would match the WHERE for ever and be rewritten on every run.
      AND jsonb_typeof(snapshot -> %(key)s) = 'object'
      AND snapshot -> %(key)s ->> 'raw' IS DISTINCT FROM %(placeholder)s
"""


def migrate(cr, version):
    total = 0
    total += _scrub_secret_named_fields(cr)
    total += _scrub_secret_config_parameters(cr)
    if total:
        # INFO, not WARNING, on purpose. This migration replays on every copy of the
        # database — each staging rebuild, each production restore into test1/test2, each
        # laptop restore — and re-redacts the same rows the restore just brought back. At
        # WARNING it turns every odoo.sh build amber for work nobody can do on that copy,
        # and a build that is always amber is one nobody reads. The rotation is a one-time
        # human task, and it is tracked where a human will find it: the `oteny-audit` skill
        # roadmap, "Rotate the credentials that were exposed", with the key list and an owner.
        _logger.info(
            "post-migrate 19.0.1.519: redacted %d audit log rows that held a credential in "
            "cleartext. Every credential involved must still be ROTATED — redacting the log "
            "does not un-expose a value every internal user could already read.",
            total,
        )
    else:
        _logger.info("post-migrate 19.0.1.519: no cleartext credentials found in the audit log")
    return total


def _scrub_secret_named_fields(cr):
    """Pass 1+2 — any model, any field whose NAME marks it as a credential.

    The field-name shape is imported from `base_patch._is_secret_field_name`, so the scrub
    and the runtime cannot disagree about which NAME is a credential. They do differ in two
    ways, and both run in the safe direction — the scrub redacts a little more, never less:

    * the runtime also applies a field-TYPE gate; a stored row carries no field object, so
      the scrub cannot. It therefore also redacts an Integer counter or a Boolean whose name
      matches (`is_token_out_of_sync` — one row on test1). The cost is a rounding error;
      going forward the runtime keeps them readable.
    * the runtime's per-class `_oteny_audit_redact_fields` cannot be read from SQL. Nothing
      in production declares it, and a migration is forward-only, so a declaration added
      later needs its own scrub anyway.

    Distinct names and distinct snapshot keys are read first, so the flat UPDATE runs against
    `field_name = ANY(...)` and uses `oteny_audit_log_field_name_create_date_idx` instead of
    a regex seq-scan.

    The snapshot UPDATE does NOT use the `oteny_audit_log_snapshot_gin_idx` GIN index:
    `%(key)s` is a bind parameter, so `jsonb_build_object(%(key)s, '{}')` is not a plan-time
    constant and the planner cannot probe GIN with it. Measured on the `test1` database on
    2026-08-25, it falls back to the partial index on the snapshot rows
    (`oteny_audit_log_snapshot_create_date_idx`) and filters: 90,445 rows scanned, 1,202
    matched, 243 ms per key. With a handful of secret keys that is well under a second, so
    the readable form is kept rather than inlining the key to court the index.
    """
    rows = 0

    cr.execute("SELECT DISTINCT field_name FROM oteny_audit_log WHERE field_name <> '__snapshot__'")
    flat_names = sorted(n for (n,) in cr.fetchall() if _is_secret_field_name(n))
    if flat_names:
        cr.execute(
            _predicate(_REDACT_FLAT_SQL, "field_name = ANY(%(names)s)"),
            {"placeholder": AUDIT_REDACTED, "names": flat_names},
        )
        rows += cr.rowcount
        _logger.info(
            "post-migrate 19.0.1.519: redacted %d update rows on secret-named fields %s",
            cr.rowcount, ", ".join(flat_names),
        )

    cr.execute(
        """
        SELECT DISTINCT k
        FROM oteny_audit_log l, LATERAL jsonb_object_keys(l.snapshot) k
        WHERE l.field_name = '__snapshot__' AND l.snapshot IS NOT NULL
        """
    )
    snapshot_keys = sorted(k for (k,) in cr.fetchall() if _is_secret_field_name(k))
    for key in snapshot_keys:
        cr.execute(
            _predicate(_REDACT_SNAPSHOT_SQL, "TRUE"),
            {"placeholder": AUDIT_REDACTED, "key": key},
        )
        rows += cr.rowcount
        _logger.info(
            "post-migrate 19.0.1.519: redacted %d snapshot rows holding '%s'", cr.rowcount, key
        )

    return rows


def _scrub_secret_config_parameters(cr):
    """Pass 3 — `ir.config_parameter.value`, where the credential is named by the sibling key.

    `record_display_name` on such a row already IS the key (`_rec_name = 'key'`), so the rows
    are selectable without joining a table whose row may since have been deleted — and a
    deleted parameter is precisely the rotated-out case worth scrubbing.

    Two gates, both imported from the runtime rule so there is one definition: the key must
    name a credential, AND the stored value must have a shape a credential can have. The
    second gate matters because this is forward-only: without it, `auth_password_policy.
    minlength` (`8`) and `portal.allow_api_keys` (`True`) would lose their value history
    permanently, and those are exactly the security settings an auditor wants to read.
    """
    rows = 0

    cr.execute(
        """
        SELECT id, record_display_name, COALESCE(old_value, ''), COALESCE(new_value, '')
        FROM oteny_audit_log
        WHERE model_name = 'ir.config_parameter'
          AND field_name = 'value'
          AND record_display_name IS NOT NULL
        """
    )
    flat_ids = [
        rid
        for rid, key, old_value, new_value in cr.fetchall()
        if is_secret_param_key(key)
        and (is_secret_param_value(old_value) or is_secret_param_value(new_value))
    ]
    if flat_ids:
        cr.execute(
            _predicate(_REDACT_FLAT_SQL, "id = ANY(%(ids)s)"),
            {"placeholder": AUDIT_REDACTED, "ids": flat_ids},
        )
        rows += cr.rowcount

    cr.execute(
        """
        SELECT id, record_display_name, COALESCE(snapshot -> 'value' ->> 'raw', '')
        FROM oteny_audit_log
        WHERE model_name = 'ir.config_parameter'
          AND field_name = '__snapshot__'
          AND record_display_name IS NOT NULL
          AND jsonb_typeof(snapshot -> 'value') = 'object'
        """
    )
    snapshot_ids = [
        rid
        for rid, key, raw in cr.fetchall()
        if is_secret_param_key(key) and is_secret_param_value(raw)
    ]
    if snapshot_ids:
        cr.execute(
            _predicate(_REDACT_SNAPSHOT_SQL, "id = ANY(%(ids)s)"),
            {"placeholder": AUDIT_REDACTED, "key": "value", "ids": snapshot_ids},
        )
        rows += cr.rowcount

    if rows:
        _logger.info(
            "post-migrate 19.0.1.519: redacted %d rows for secret system parameters", rows
        )
    return rows
