{
    'name': "Riverflow",
    'version': '1.4',
    'depends': [
        'base',
        'mail',
    ],
    'author': "Vriend Studio",
    'category': 'hr',
    'description': """
    Task manager for the Service Industry
    """,
    # data files always loaded at installation
    'data': [
        'security/ir.model.access.csv',
        'wizards/riverflow_service_wizard_view.xml',
        'views/riverflow_service_views.xml',
        'views/riverflow_workflow_views.xml',
        'views/riverflow_workflow_state_views.xml',
        'views/riverflow_workflow_transition_views.xml',
        'views/riverflow_workflow_transition_action_views.xml',
        'data/workflow_transition_action_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'riverflow/static/src/components/**/*',
        ],
    },
    'application': True,
    'auto_install': False,
    'license': 'OEEL-1'
}
