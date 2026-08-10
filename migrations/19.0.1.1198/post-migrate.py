"""19.0.1.1198 (post): workflow cleanup + icon fix (icon-audit 2026-08-10).

1. Send Notification icon fa-envelope -> fa-bell. Send Email
   (await-reply) owns the envelope and both sit side by side in the
   same workflow picker; the bell marks the one-shot notification
   variant. The data file is ``noupdate="1"``, so the XML change alone
   never reaches existing databases; guarded on the shipped icon so a
   manual override survives.

2. RETIRE the "To Be Invoiced" workflow stub. It never went live:
   zero services on production, three states but its transitions were
   never uncommented, and its icon (fa-file-invoice-dollar) was an
   FA5-only name rendering as an empty box. The XML file is removed;
   because it was ``noupdate="1"`` data the live rows survive the -u,
   so this migration deletes them (states first, then the workflow —
   ORM unlink also removes the ir_model_data rows). Guarded: if any
   service references the workflow after all, the deletion is skipped
   and logged instead of breaking the upgrade.

3. Archive the hand-made "AB Appointment (Do not use, work in
   progress)" workflow found on production: created via the UI (no
   XML id), zero attached services, explicitly named do-not-use —
   superseded by the real Arrange Work Permit workflow. Matched by
   exact name + absence of an XML id + zero usage, so the guard cannot
   hit a shipped or in-use workflow. Archive (not delete): it is
   hand-entered data we do not own.

Idempotent: every step is search-then-act.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

HANDMADE_ARCHIVE_NAME = "AB Appointment (Do not use, work in progress)"


def _fix_send_notification_icon(env):
    workflow = env.ref(
        "riverflow.workflow_service_send_notification", raise_if_not_found=False
    )
    if workflow and workflow.icon == "fa-envelope":
        workflow.icon = "fa-bell"
        _logger.info("Send Notification workflow icon updated fa-envelope -> fa-bell")


def _retire_to_be_invoiced(env):
    workflow = env.ref("riverflow.workflow_to_be_invoiced", raise_if_not_found=False)
    if not workflow:
        return
    services = env["riverflow.service"].with_context(active_test=False).search(
        [
            "|",
            ("workflow_id", "=", workflow.id),
            ("front_office_workflow_id", "=", workflow.id),
        ],
        limit=1,
    )
    if services:
        _logger.warning(
            "To Be Invoiced workflow unexpectedly has services (e.g. %s) — "
            "skipping retirement",
            services.ids,
        )
        return
    states = env["riverflow.state"].with_context(active_test=False).search(
        [("workflow_id", "=", workflow.id)]
    )
    states.unlink()
    workflow.unlink()
    _logger.info("Retired the unused To Be Invoiced workflow stub (+%d states)", len(states))


def _archive_handmade_ab_appointment(env):
    workflows = env["riverflow.workflow"].with_context(active_test=False).search(
        [("name", "=", HANDMADE_ARCHIVE_NAME), ("active", "=", True)]
    )
    for workflow in workflows:
        has_xmlid = env["ir.model.data"].search_count(
            [("model", "=", "riverflow.workflow"), ("res_id", "=", workflow.id)]
        )
        in_use = env["riverflow.service"].with_context(active_test=False).search_count(
            [
                "|",
                ("workflow_id", "=", workflow.id),
                ("front_office_workflow_id", "=", workflow.id),
            ]
        )
        if not has_xmlid and not in_use:
            workflow.active = False
            _logger.info("Archived hand-made workflow %s (id %s)", workflow.name, workflow.id)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _fix_send_notification_icon(env)
    _retire_to_be_invoiced(env)
    _archive_handmade_ab_appointment(env)
