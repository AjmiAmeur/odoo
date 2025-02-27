# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields

class HrDomaineDiscipline(models.Model):
    _name = 'hr.domaine.discipline'
    _description = 'liste des discipline académique par domaine'
    _order = "code asc"
    
   

    name = fields.Char(string="nom discipline", help="Discipline académique par domaine.", required=True, translate=True)
    code = fields.Char(string='Code discipline', size=4, required=True)
    domaine_id = fields.Many2one('hr.domaine', string="Domaine", required=True)



    _sql_constraints = [
        ('code_uniq', 'unique (code)', "code discipline deja existe!"),
    ]
