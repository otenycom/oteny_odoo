{
    "name": "Riverflow",
    "version": "18.0.1.294",
    "depends": ["base", "mail", "documents"],
    "author": "Vriend Studio",
    "category": "Workflow",
    "description": """
    Task manager for the Service Industry
    """,
    # data files always loaded at installation
    "data": [
        "security/ir.model.access.csv",
        "data/riverflow_teams_data.xml",
        "wizards/riverflow_transition_wizard_view.xml",
        "wizards/riverflow_service_wizard_view.xml",
        "wizards/riverflow_start_service_view.xml",
        "wizards/riverflow_service_email_sender_view.xml",
        "views/riverflow_service_views.xml",
        "views/riverflow_workflow_views.xml",
        "views/riverflow_state_views.xml",
        "views/riverflow_transition_views.xml",
        "views/riverflow_transition_action_views.xml",
        "views/riverflow_state_record_views.xml",
        "views/riverflow_team_views.xml",
        "views/auto_add_service_views.xml",
        "views/res_config_settings_views.xml",
        "data/transition_action_data.xml",
        "data/service_email_workflow.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "riverflow/static/src/components/**/*",
        ],
    },
    "application": True,
    "auto_install": False,
    "license": "OEEL-1",
}
