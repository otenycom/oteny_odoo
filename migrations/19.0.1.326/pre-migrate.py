"""Repair orphan discuss_channel_member rows left behind by AI chat autovacuum.

Background
----------
Odoo's AI module (`ai/models/discuss_channel.py::_remove_ai_chat_channels`)
has an @api.autovacuum that deletes any ai_chat channel with
`last_interest_dt < -1d`. Channels are unlinked via ORM, which relies on the
DB FK `discuss_channel_member_channel_id_fkey` (ON DELETE cascade) to clean
up member rows.

On this workspace's production and local restores, that FK went missing at
some point -- likely dropped during a past failed upgrade or manual DB
surgery -- and the autovacuum has since been leaking orphan member rows.
On any upgrade whose scope happens to queue the FK for validation
(`check_foreign_keys`), `ADD CONSTRAINT` fails because of pre-existing
orphans.

Why this migration lives in oteny_audit (not crewradar_wilma)
-------------------------------------------------------------
The FK violation fires during `riverflow`'s init_models (module 114/166,
the first in the upgrade scope that pulls `discuss.channel.member` into
`_foreign_keys` via its _inherit graph). `crewradar_wilma` loads much later
in the graph, so a pre-migration there runs too late. `oteny_audit` loads
at ~47/166 (before riverflow), depends on `mail`, and is always part of
the crewradar -u scope. That makes it the right place for a cross-cutting
mail-table repair without violating module boundaries (mail is a declared
dependency).

What it does
------------
1. DELETE orphan `discuss_channel_member` rows (channel no longer exists).
   This matches the behavior Odoo core expects (the FK is ON DELETE
   cascade, so these rows should have been cleaned when the channel was
   unlinked; they only survived because the FK was absent).
2. Re-add the FK if missing, so future channel autovacuum runs cascade
   correctly and the gap cannot reopen before the next broad upgrade.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM discuss_channel_member
        WHERE channel_id NOT IN (SELECT id FROM discuss_channel)
        """
    )
    orphan_members = cr.rowcount
    if orphan_members:
        _logger.warning(
            "pre-migrate 19.0.1.326: deleted %d orphan discuss_channel_member "
            "rows whose channel had been autovacuumed (FK was missing so "
            "cascade did not fire)",
            orphan_members,
        )

    cr.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'discuss_channel_member_channel_id_fkey'
        """
    )
    if not cr.fetchone():
        cr.execute(
            """
            ALTER TABLE discuss_channel_member
            ADD CONSTRAINT discuss_channel_member_channel_id_fkey
            FOREIGN KEY (channel_id) REFERENCES discuss_channel(id)
            ON DELETE CASCADE
            """
        )
        _logger.warning(
            "pre-migrate 19.0.1.326: re-added missing FK "
            "discuss_channel_member_channel_id_fkey (ON DELETE cascade). "
            "Future channel autovacuum runs will now cascade cleanly."
        )
