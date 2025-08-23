{
    "name": "oteny_audit",
    "version": "18.0.1.630",
    "depends": ["base"],
    "author": "Oteny.com",
    "category": "Audit",
    "description": """
    Audit Module by Oteny.com for Odoo
    """,
    "data": [
        "security/ir.model.access.csv",
        "views/oteny_audit_log_views.xml",
    ],
    # "assets": {
    #     "web.assets_backend": [
    #         "riveraudit/static/src/components/**/*",
    #     ],
    # },
    "demo": [],
    "application": True,
    "auto_install": False,
    "license": "OEEL-1",
}
