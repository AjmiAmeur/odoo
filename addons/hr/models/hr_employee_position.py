# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import randint
from odoo import models, fields

class HREmployeePosition(models.Model):
    _name = 'hr.employee.position'
    _description = "Positions administratives"
    _order = "name"
   
    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string="Position administrative", required=True, translate=True)
    # color = fields.Integer(string='Color Index', default=_get_default_color)
    # employee_ids = fields.One2many('hr.employee', 'position_id', string='Employees' ,readonly=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Position administrative deja existe !"),
    ]
