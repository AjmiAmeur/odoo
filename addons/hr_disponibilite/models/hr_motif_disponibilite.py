# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrhrMotifDisponibilite(models.Model):
    _name = 'hr.motif.disponibilite'
    _description = 'Motif de mise en disponibilité'
    _order = 'sequence'

    active = fields.Boolean(default=True)
    name = fields.Char(string='Motif', required=True, index='trigram',help='Motif de mise en disponibilité.', translate=True)
    sequence = fields.Integer(default=10)