# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Gestion des mises en disponibilité des employés',
    'version': '1.0',
    'category': 'Human Resources/disponibilites',
    'sequence': 340,
    'description': """
Add all information on the employee form to manage disponibilites.
=============================================================

    * disponibilite
    * Place of Birth,
    * Medical Examination Date
    * Company Vehicle

You can assign several disponibilites per employee.
    """,
    'website': 'https://www.odoo.com/app/employees',
    'depends': ['hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/hr_disponibilite_data.xml',
        'report/hr_disponibilite_history_report_views.xml',
        'views/hr_disponibilite_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/hr_departure_wizard_views.xml',
    ],
    'demo': ['data/hr_disponibilite_demo.xml'],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            'hr_disponibilite/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
