"""Post-migration script for riverflow 19.0.1.1025.

Set weekend_deadline_rule on all existing services using a structural rule
based on use_project_deadline_from and days_relative_to_project:

- use_project_deadline_from = 'self' -> 'allow' (default, no update needed)
- non-'self' with days_relative_to_project <= 0 -> 'friday_before'
- non-'self' with days_relative_to_project > 0  -> 'monday_after'

This covers both templates and live service instances. The write() triggers
_compute_deadline recomputation, so existing weekend deadlines shift
automatically to the correct Friday or Monday.
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Service = env["riverflow.service"].with_context(active_test=False)

    # Services with computed deadlines and offset <= 0: bring to Friday
    friday_services = Service.search([
        ("use_project_deadline_from", "!=", "self"),
        ("days_relative_to_project", "<=", 0),
    ])
    friday_count = len(friday_services)
    if friday_services:
        friday_services.write({"weekend_deadline_rule": "friday_before"})
    _logger.info(
        "Post-migration 19.0.1.1025: Set weekend_deadline_rule='friday_before' on %d services",
        friday_count,
    )

    # Services with computed deadlines and offset > 0: delay to Monday
    monday_services = Service.search([
        ("use_project_deadline_from", "!=", "self"),
        ("days_relative_to_project", ">", 0),
    ])
    monday_count = len(monday_services)
    if monday_services:
        monday_services.write({"weekend_deadline_rule": "monday_after"})
    _logger.info(
        "Post-migration 19.0.1.1025: Set weekend_deadline_rule='monday_after' on %d services",
        monday_count,
    )

    _logger.info(
        "Post-migration 19.0.1.1025 complete: %d friday_before + %d monday_after = %d services updated",
        friday_count,
        monday_count,
        friday_count + monday_count,
    )
