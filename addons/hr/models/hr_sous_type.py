# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import randint
from odoo import models, fields

class HrEmployeeSousType(models.Model):
    _name = 'hr.sous.type'
    _description = 'sous-types des employés'
    _order = "type,name"


    name = fields.Char(string="Sous-type", help="sous-types des employés.", required=True, translate=True)
    type = fields.Selection([
        ('employee', 'Personnels IATOS'),
        ('enseignant', 'Enseignant'),
        ('visiteur', 'Visiteur'),
        ('vacataire', 'Vacataire'),
        ('student', 'Etudiant'),
        ('trainee', 'Stagiaire'),  
        ('other', 'Autre'),
        ], string="Types d'employé", default='employee', required=True, groups="hr.group_hr_user",
        help="Administratif/Enseignant/Visiteur/vacataire/Etudiant/Stagiaire/Autre")

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Sous-Type deja existe!"),
    ]
