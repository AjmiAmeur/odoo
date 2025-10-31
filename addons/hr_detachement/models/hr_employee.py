# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from pytz import timezone, UTC
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.addons.resource.models.utils import Intervals
from odoo.exceptions import UserError


class EmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    first_detachement_date = fields.Date(compute='_compute_manager_only_fields', search='_search_first_detachement_date')

    def _get_manager_only_fields(self):
        return super()._get_manager_only_fields() + ['first_detachement_date']

    def _search_first_detachement_date(self, operator, value):
        employees = self.env['hr.employee'].sudo().search([('id', 'child_of', self.env.user.employee_id.ids), ('first_detachement_date', operator, value)])
        return [('id', 'in', employees.ids)]


class EmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    @api.model
    def _get_new_hire_field(self):
        return 'first_detachement_date'


class Employee(models.Model):
    _inherit = "hr.employee"

    legal_name = fields.Char(compute='_compute_legal_name', store=True, readonly=False, groups="hr.group_hr_user")
    detachement_ids = fields.One2many('hr.detachement', 'employee_id', string='Employee Detachements', groups="hr.group_hr_user")
    detachement_id = fields.Many2one(
        'hr.detachement', string='Détachement actuel', groups="hr.group_hr_user",
        domain="[('company_id', '=', company_id), ('employee_id', '=', id)]", help='Détachement actuel de l’employé', copy=False)
    detachements_count = fields.Integer(compute='_compute_detachements_count', string='Detachement Count', groups="hr.group_hr_user")
    detachement_warning = fields.Boolean(string='Detachement Warning', store=True, compute='_compute_detachement_warning', groups="hr.group_hr_user")
    first_detachement_date = fields.Date(compute='_compute_first_detachement_date', groups="hr.group_hr_user", store=True)

    @api.depends('name')
    def _compute_legal_name(self):
        for employee in self:
            if not employee.legal_name:
                employee.legal_name = employee.name

    def _get_first_detachements(self):
        self.ensure_one()
        detachements = self.sudo().detachement_ids.filtered(lambda c: c.state != 'cancel')
        if self.env.context.get('before_date'):
            detachements = detachements.filtered(lambda c: c.date_start <= self.env.context['before_date'])
        return detachements

    def _get_first_detachement_date(self, no_gap=True):
        self.ensure_one()

        def remove_gap(detachements):
            # We do not consider a gap of more than 4 days to be a same occupation
            # detachements are considered to be ordered correctly
            if not detachements:
                return self.env['hr.detachement']
            if len(detachements) == 1:
                return detachements
            current_detachement = detachements[0]
            older_detachements = detachements[1:]
            current_date = current_detachement.date_start
            for i, other_detachement in enumerate(older_detachements):
                # Consider current_detachement.date_end being false as an error and cut the loop
                gap = (current_date - (other_detachement.date_end or date(2100, 1, 1))).days
                current_date = other_detachement.date_start
                if gap >= 4:
                    return older_detachements[0:i] + current_detachement
            return older_detachements + current_detachement

        detachements = self._get_first_detachements().sorted('date_start', reverse=True)
        if no_gap:
            detachements = remove_gap(detachements)
        return min(detachements.mapped('date_start')) if detachements else False

    @api.depends('detachement_ids.state', 'detachement_ids.date_start')
    def _compute_first_detachement_date(self):
        for employee in self:
            employee.first_detachement_date = employee._get_first_detachement_date()

    @api.depends('detachement_id', 'detachement_id.state', 'detachement_id.kanban_state')
    def _compute_detachement_warning(self):
        """Calcule le warning de détachement et met à jour la position administrative."""
        # Récupération des positions une seule fois (optimisation)
        detachement_position = self.env['hr.employee.position'].search([('name', '=', 'Détachement')], limit=1)
        default_position = self.env['hr.employee.position'].browse(1)

        for employee in self:
            det = employee.detachement_id

            # Calcul du warning selon l'état du détachement
            warning = (not det or det.kanban_state == 'blocked' or det.state != 'open')
            employee.detachement_warning = warning

            # Mise à jour automatique du poste administratif
            if not warning and detachement_position:
                # Si détachement actif et valide
                employee.position_id = detachement_position.id   # affectation correcte
            elif warning:
                # Si détachement invalide ou bloqué
                if default_position:
                    employee.position_id = default_position.id   # retour à la position par défaut
                else:
                    employee.position_id = False                 # 🔹 vide si pas de position par défaut


    def _compute_detachements_count(self):
        # read_group as sudo, since detachement count is displayed on form view
        detachement_histories = self.env['hr.detachement.history'].sudo().search([('employee_id', 'in', self.ids)])
        for employee in self:
            detachement_history = detachement_histories.filtered(lambda ch: ch.employee_id == employee)
            employee.detachements_count = detachement_history.detachement_count

    def _get_detachements(self, date_from, date_to, states=['open'], kanban_state=False):
        """
        Returns the detachements of the employee between date_from and date_to
        """
        state_domain = [('state', 'in', states)]
        if kanban_state:
            state_domain = expression.AND([state_domain, [('kanban_state', 'in', kanban_state)]])

        return self.env['hr.detachement'].search(
            expression.AND([[('employee_id', 'in', self.ids)],
            state_domain,
            [('date_start', '<=', date_to),
                '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_from)]]))

    def _get_incoming_detachements(self, date_from, date_to):
        return self._get_detachements(date_from, date_to, states=['draft'], kanban_state=['done'])
    @api.model
    def _get_all_detachements(self, date_from, date_to, states=['open']):
        """
        Returns the detachements of all employees between date_from and date_to
        """
        return self.search(['|', ('active', '=', True), ('active', '=', False)])._get_detachements(date_from, date_to, states=states)

    def write(self, vals):
        res = super().write(vals)
        
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_open_detachement(self):
        if any(detachement.state == 'open' for detachement in self.detachement_ids):
            raise UserError(_('You cannot delete an employee with a running detachement.'))

    def action_open_detachement(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_detachement.action_hr_detachement')
        action['views'] = [(False, 'form')]
        if not self.detachement_ids:
            action['context'] = {
                'default_employee_id': self.id,
                'from_action_open_detachement': True,
            }
            action['target'] = 'current'
            return action

        target_detachement = self.detachement_id
        if target_detachement:
            action['res_id'] = target_detachement.id
            return action

        target_detachement = self.detachement_ids.filtered(lambda c: c.state == 'draft')
        if target_detachement:
            action['res_id'] = target_detachement[0].id
            return action

        action['res_id'] = self.detachement_ids[0].id
        return action
