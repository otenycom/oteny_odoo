"""Post-migration script for riverflow 19.0.1.1024.

Add missing transitions to the Train Ticket workflow:
- Booked → Not Started  (step back, fa-undo)
- Booked → Cancelled    (cancel)
- Registered → Cancelled (cancel)

These are new XML records and Odoo will create them automatically on module
update (noupdate="1" only prevents updating existing records). This migration
acts as an explicit safety net for the live system.
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# New transitions to ensure exist: (xml_id, from_state_xml_id, to_state_xml_id, vals)
NEW_TRANSITIONS = [
    (
        "riverflow.trans_train_booked_to_not_started",
        "riverflow.state_train_booked",
        "riverflow.state_train_not_started",
        {
            "name": "Back to Not Started",
            "sequence": 30,
            "icon": "fa-undo",
        },
    ),
    (
        "riverflow.trans_train_booked_to_cancelled",
        "riverflow.state_train_booked",
        "riverflow.state_train_cancelled",
        {
            "name": "Cancel",
            "sequence": 40,
        },
    ),
    (
        "riverflow.trans_train_registered_to_cancelled",
        "riverflow.state_train_registered",
        "riverflow.state_train_cancelled",
        {
            "name": "Cancel",
            "sequence": 20,
        },
    ),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info("Post-migration 19.0.1.1024: Adding missing Train Ticket workflow transitions")

    action_default = env.ref("riverflow.transition_action_default")
    Transition = env["riverflow.transition"]
    IrModelData = env["ir.model.data"]

    created = 0
    for xml_id, from_xml_id, to_xml_id, extra_vals in NEW_TRANSITIONS:
        # Skip if the record was already created (e.g. by XML loading on update)
        module, name = xml_id.split(".")
        existing_data = IrModelData.search(
            [("module", "=", module), ("name", "=", name)], limit=1
        )
        if existing_data:
            _logger.info(f"Transition {xml_id} already exists, skipping")
            continue

        from_state = env.ref(from_xml_id)
        to_state = env.ref(to_xml_id)

        vals = {
            "from_state_id": from_state.id,
            "to_state_id": to_state.id,
            "action_id": action_default.id,
            **extra_vals,
        }
        transition = Transition.create(vals)

        # Register the external ID so subsequent updates recognise this record
        IrModelData.create(
            {
                "module": module,
                "name": name,
                "model": "riverflow.transition",
                "res_id": transition.id,
                "noupdate": True,
            }
        )
        _logger.info(
            f"Created transition {xml_id}: '{vals['name']}' "
            f"(from={from_state.name} → to={to_state.name}, id={transition.id})"
        )
        created += 1

    _logger.info(f"Post-migration 19.0.1.1024 complete: {created} transition(s) created")
