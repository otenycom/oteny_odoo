"""Promote popular ir.filters to view shortcuts.

Finds existing favorites for riverflow.state.record that are either
default filters or shared with at least 3 users, and enables them
as shortcut banner buttons.
"""
import logging

_logger = logging.getLogger(__name__)

CALENDAR_FILTER_NAMES = {"Crewchanges OPS", "HR To-do Radar"}


def migrate(cr, version):
    # Find filters that are default OR have 3+ users assigned.
    # user_ids is a many2many, so we count via the relation table.
    cr.execute("""
        SELECT f.id, f.name
        FROM ir_filters f
        LEFT JOIN ir_filters_res_users_rel rel ON rel.ir_filters_id = f.id
        WHERE f.model_id = 'riverflow.state.record'
          AND f.active = true
        GROUP BY f.id, f.name
        HAVING f.is_default = true
           OR COUNT(rel.res_users_id) >= 3
        ORDER BY f.name
    """)
    rows = cr.fetchall()
    if not rows:
        _logger.info("No filters to promote to shortcuts.")
        return

    # Split into two groups: HR filters get sequence starting at 100,
    # all others start at 10.
    hr_rows = [(fid, name) for fid, name in rows if name.startswith("HR")]
    other_rows = [(fid, name) for fid, name in rows if not name.startswith("HR")]

    seq = 10
    for filter_id, filter_name in other_rows:
        view_type = "calendar" if filter_name in CALENDAR_FILTER_NAMES else "list"
        cr.execute("""
            UPDATE ir_filters
            SET shortcut_sequence = %s,
                shortcut_view_type = %s
            WHERE id = %s
        """, (seq, view_type, filter_id))
        _logger.info(
            "Promoted filter %r (id=%s) to shortcut: seq=%s, view=%s",
            filter_name, filter_id, seq, view_type,
        )
        seq += 10

    seq = 100
    for filter_id, filter_name in hr_rows:
        view_type = "calendar" if filter_name in CALENDAR_FILTER_NAMES else "list"
        cr.execute("""
            UPDATE ir_filters
            SET shortcut_sequence = %s,
                shortcut_view_type = %s
            WHERE id = %s
        """, (seq, view_type, filter_id))
        _logger.info(
            "Promoted filter %r (id=%s) to shortcut: seq=%s, view=%s",
            filter_name, filter_id, seq, view_type,
        )
        seq += 10
