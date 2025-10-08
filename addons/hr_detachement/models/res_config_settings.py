# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    detachement_expiration_notice_period = fields.Integer(string="detachement Expiry Notice Period", related='company_id.detachement_expiration_notice_period', readonly=False)
    work_permit_expiration_notice_period = fields.Integer(string="Work Permit Expiry Notice Period", related='company_id.work_permit_expiration_notice_period', readonly=False)
