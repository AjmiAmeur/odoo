# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _
from odoo.exceptions import UserError


class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    def _get_employee_departure_date(self):
        employee = self.env['hr.employee'].browse(self.env.context['active_id'])
        if employee.detachement_id.state == "open":
            return False
        expired_detachement = self.env['hr.detachement'].search([('employee_id', '=', employee.id), ('state', '=', 'close')], limit=1, order='date_end desc')
        if expired_detachement:
            return expired_detachement.date_end
        return super()._get_employee_departure_date()

    set_date_end = fields.Boolean(string="Set Detachement End Date", default=lambda self: self.env.user.has_group('hr_detachement.group_hr_detachement_manager'),
        help="Set the end date on the current detachement.")

    def action_register_departure(self):
        """If set_date_end is checked, set the departure date as the end date to current running detachement,
        and cancel all draft detachements"""
        current_detachement = self.sudo().employee_id.detachement_id
        if current_detachement and current_detachement.date_start > self.departure_date:
            raise UserError(_("Departure date can't be earlier than the start date of current detachement."))

        super(HrDepartureWizard, self).action_register_departure()
        if self.set_date_end:
            self.sudo().employee_id.detachement_ids.filtered(lambda c: c.state == 'draft').write({'state': 'cancel'})
            if current_detachement and current_detachement.state in ['open', 'draft']:
                self.sudo().employee_id.detachement_id.write({'date_end': self.departure_date})
            if current_detachement.state == 'open':
                current_detachement.state = 'close'
