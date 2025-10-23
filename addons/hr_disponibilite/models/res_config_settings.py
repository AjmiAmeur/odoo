# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    disponibilite_expiration_notice_period = fields.Integer(string="Préavis d’expiration de la mise en disponibilité", related='company_id.disponibilite_expiration_notice_period', readonly=False)
    work_permit_expiration_notice_period = fields.Integer(string="Préavis d’expiration du permis de travail", related='company_id.work_permit_expiration_notice_period', readonly=False)
