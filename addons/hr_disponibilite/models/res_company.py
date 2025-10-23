# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    disponibilite_expiration_notice_period = fields.Integer("Préavis d’expiration de la mise en disponibilité", default=7)
    work_permit_expiration_notice_period = fields.Integer("Préavis d’expiration du permis de travail", default=60)
