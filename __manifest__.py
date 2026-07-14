{
    "name": "View Shortcuts",
    "version": "19.0.1.161",  # 19.0.1.161: shortcut banner view-type icon now resolved from session.view_info (the server-side ir.ui.view._get_view_info map the view switcher uses) instead of a hardcoded list/calendar t-if, so custom view types (e.g. rivercreds_plan_timeline) get their registered icon automatically.
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
