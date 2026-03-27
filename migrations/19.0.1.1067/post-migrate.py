"""Set has_supply_time=True on Taxi and Train workflows.

These workflow XML records are noupdate=1, so they won't pick up the new
field from the XML data on module upgrade. This migration sets the flag
on existing workflows so that taxi and train services show the time-of-day
field on the Supply Order tab.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Workflow = env["riverflow.workflow"]

    taxi_wf = env.ref("riverflow.workflow_service_taxi_order", raise_if_not_found=False)
    train_wf = env.ref("riverflow.workflow_service_train_ticket", raise_if_not_found=False)

    workflows = Workflow.browse()
    if taxi_wf:
        workflows |= taxi_wf
    if train_wf:
        workflows |= train_wf

    if workflows:
        workflows.write({"has_supply_time": True})
