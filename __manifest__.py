{
    "name": "View Shortcuts",
    "version": "19.0.1.206",  # 19.0.1.205: Store Layout wizard gets a Period choice — a captured custom period (range_id/start_date/stop_date, the timeline views) is stored as fixed dates or, on request, relative to today in whole months from the start of today's month (relative_period {start_month_offset, months}); offsets prefilled from the captured dates and editable. The summary also lists unknown layout keys instead of 'No layout data captured'.  # 19.0.1.163: Shortcut View field is now a dynamic selection (ir.filters._shortcut_view_type_selection) listing every switchable view type from ir.ui.view — custom view types (e.g. the credential timeline) appear automatically, no per-module selection_add. New shortcut_view_type_whitelist (Json, per-model compute) + the filterable_selection widget (whitelist_fname) narrow the dropdown to view types the filter's model actually has.  # 19.0.1.162: onShortcutClick only calls switchView when the target shortcut_view_type is among the current action's viewSwitcherEntries — a favorite whose preferred view isn't exposed by this action no longer throws ViewNotFoundError; the filter is applied in place instead.  # 19.0.1.161: shortcut banner view-type icon now resolved from session.view_info (the server-side ir.ui.view._get_view_info map the view switcher uses) instead of a hardcoded list/calendar t-if, so custom view types (e.g. rivercreds_plan_timeline) get their registered icon automatically.
    "depends": ["web"],
    "author": "Oteny",
    "category": "Tools",
    "description": """
    Extends ir.filters with shortcut fields so saved Favorites can appear
    as quick-access buttons in a banner above list and calendar views.
    Any view can opt in via js_class="shortcut_list" or js_class="shortcut_calendar".
    """,
    "data": [
        "security/ir.model.access.csv",
        "wizard/store_layout_wizard_views.xml",
        "views/ir_filters_views.xml",
        "data/ir_config_parameter_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "oteny_shortcut/static/src/components/**/*",
            "oteny_shortcut/static/src/views/**/*",
        ],
    },
    "auto_install": False,
    "license": "OEEL-1",
}
