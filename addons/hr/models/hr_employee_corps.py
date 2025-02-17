# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import randint
from odoo import models, fields

class HrEmployeeCorps(models.Model):
    _name = 'hr.employee.corps'
    _description = 'Corps des administrations publiques'
    _order = "name"


    
    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string="Corps", help="Corps des administrations publiques.", required=True, translate=True)
    # color = fields.Integer(string='Color Index', default=_get_default_color)
    # employee_ids = fields.One2many('hr.employee', 'corps_id', string='Employees')
    type = fields.Selection([
        ('employee', 'Administratif'),
        ('enseignant', 'Enseignant'),
        ('visiteur', 'Visiteur'),
        ('vacataire', 'Vacataire'),
        ('student', 'Etudiant'),
        ('trainee', 'Stagiaire'),  
        ('other', 'Autre'),
        ], string="Types d'employé", default='employee', required=True, groups="hr.group_hr_user",
        help="Administratif/Enseignant/Visiteur/vacataire/Etudiant/Stagiaire/Autre")

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Corps deja existe!"),
    ]
