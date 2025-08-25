{
    "name": "oteny_audit",
    "version": "18.0.1.0.0",
    "depends": ["base"],
    "author": "Oteny.com",
    "category": "Extra Tools",
    "description": """
    Audit Module by Oteny.com for Odoo
    """,
    "data": [
        "security/ir.model.access.csv",
        "views/oteny_audit_log_views.xml",
        "views/oteny_audit_log_aggregated_views.xml",
    ],
    # "assets": {
    #     "web.assets_backend": [
    #         "riveraudit/static/src/components/**/*",
    #     ],
    # },
    "demo": [],
    "application": True,
    "auto_install": True,
    "license": "OPL-1",
}
