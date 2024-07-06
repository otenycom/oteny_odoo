{
    'name': "River Flow",
    'version': '1.3',
    'depends': [
        'base',
        'mail',
    ],
    'author': "Vriend Studio",
    'category': 'hr',
    'description': """
    Service Industry workflow module
    """,
    # data files always loaded at installation
   'data': [
        'security/ir.model.access.csv',
        'views/riverflow_service_views.xml',
        'wizards/riverflow_service_wizard_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'riverflow/static/src/components/**/*',
        ],
    },
    'application': True,
    'auto_install': True,
    'license': 'OEEL-1'
}