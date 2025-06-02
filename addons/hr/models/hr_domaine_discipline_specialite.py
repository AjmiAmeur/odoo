# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields

class HrDomaineDisciplineSpecialite(models.Model):
    _name = 'hr.domaine.discipline.specialite'
    _description = 'liste des spécialités académique par domaine et discipline'
    _order = "code asc"
    
   

    name = fields.Char(string="Nom Spécialité", help="spécialiténe académique par domaine et discipline.", required=True, translate=True)
    code = fields.Char(string='Code Spécialité', size=5, required=True)
    domaine_id = fields.Many2one('hr.domaine', string="Domaine", required=True)
    discipline_id = fields.Many2one('hr.domaine.discipline', string="Discipline", required=True,domain="[('domaine_id', '=?', domaine_id)]",groups="hr.group_hr_user")


    _sql_constraints = [
        ('code_uniq', 'unique (code)', "Code Spécialité deja existe!"),
    ]
