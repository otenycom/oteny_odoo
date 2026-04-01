{
    "name": "View Shortcuts",
    "version": "19.0.1.48",
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
