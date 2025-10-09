# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Détachement des employés',
    'version': '1.0',
    'category': 'Human Resources/Detachements',
    'sequence': 340,
    'description': """
Add all information on the employee form to manage detachements.
=============================================================

    * Detachement
    * Place of Birth,
    * Medical Examination Date
    * Company Vehicle

You can assign several detachements per employee.
    """,
    'website': 'https://www.odoo.com/app/employees',
    'depends': ['hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/hr_detachement_data.xml',
        'report/hr_detachement_history_report_views.xml',
        'views/hr_detachement_views.xml',
        'views/hr_employee_views.xml',
        'views/resource_calendar_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/hr_departure_wizard_views.xml',
    ],
    'demo': ['data/hr_detachement_demo.xml'],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            'hr_detachement/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
