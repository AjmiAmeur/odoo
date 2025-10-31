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

    first_disponibilite_date = fields.Date(compute='_compute_manager_only_fields', search='_search_first_disponibilite_date')

    def _get_manager_only_fields(self):
        return super()._get_manager_only_fields() + ['first_disponibilite_date']

    def _search_first_disponibilite_date(self, operator, value):
        employees = self.env['hr.employee'].sudo().search([('id', 'child_of', self.env.user.employee_id.ids), ('first_disponibilite_date', operator, value)])
        return [('id', 'in', employees.ids)]


class EmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    @api.model
    def _get_new_hire_field(self):
        return 'first_disponibilite_date'


class Employee(models.Model):
    _inherit = "hr.employee"

    disponibilite_ids = fields.One2many('hr.disponibilite', 'employee_id', string='Mises en disponibilité de l’employé', groups="hr.group_hr_user")
    disponibilite_id = fields.Many2one(
        'hr.disponibilite', string='Mise en disponibilité actuelle', groups="hr.group_hr_user",
        domain="[('company_id', '=', company_id), ('employee_id', '=', id)]", help='Current disponibilite of the employee', copy=False)
    disponibilites_count = fields.Integer(compute='_compute_disponibilites_count', string='Nombre de mises en disponibilité', groups="hr.group_hr_user")
    disponibilite_warning = fields.Boolean(string='Alerte de mise en disponibilité', store=True, compute='_compute_disponibilite_warning', groups="hr.group_hr_user")
    first_disponibilite_date = fields.Date(string='Date de première mise en disponibilité',compute='_compute_first_disponibilite_date', groups="hr.group_hr_user", store=True)

    
    def _get_first_disponibilites(self):
        self.ensure_one()
        disponibilites = self.sudo().disponibilite_ids.filtered(lambda c: c.state != 'cancel')
        if self.env.context.get('before_date'):
            disponibilites = disponibilites.filtered(lambda c: c.date_start <= self.env.context['before_date'])
        return disponibilites

    def _get_first_disponibilite_date(self, no_gap=True):
        self.ensure_one()

        def remove_gap(disponibilites):
            # We do not consider a gap of more than 4 days to be a same occupation
            # disponibilites are considered to be ordered correctly
            if not disponibilites:
                return self.env['hr.disponibilite']
            if len(disponibilites) == 1:
                return disponibilites
            current_disponibilite = disponibilites[0]
            older_disponibilites = disponibilites[1:]
            current_date = current_disponibilite.date_start
            for i, other_disponibilite in enumerate(older_disponibilites):
                # Consider current_disponibilite.date_end being false as an error and cut the loop
                gap = (current_date - (other_disponibilite.date_end or date(2100, 1, 1))).days
                current_date = other_disponibilite.date_start
                if gap >= 4:
                    return older_disponibilites[0:i] + current_disponibilite
            return older_disponibilites + current_disponibilite

        disponibilites = self._get_first_disponibilites().sorted('date_start', reverse=True)
        if no_gap:
            disponibilites = remove_gap(disponibilites)
        return min(disponibilites.mapped('date_start')) if disponibilites else False

    @api.depends('disponibilite_ids.state', 'disponibilite_ids.date_start')
    def _compute_first_disponibilite_date(self):
        for employee in self:
            employee.first_disponibilite_date = employee._get_first_disponibilite_date()

    @api.depends('disponibilite_id', 'disponibilite_id.state', 'disponibilite_id.kanban_state')
    def _compute_disponibilite_warning(self):
        """Calcule le warning de mise en disponibilité et met à jour la position administrative."""
        # Récupération des positions une seule fois (optimisation)
        disponibilite_position = self.env['hr.employee.position'].search([('name', '=', 'Mise en Disponibilité')], limit=1)
        default_position = self.env['hr.employee.position'].browse(1)

        for employee in self:
            det = employee.disponibilite_id

            # Calcul du warning selon l'état du mise en disponibilité 
            # state :('draft', 'New'),       ('open', 'Running'),        ('close', 'Expired'),        ('cancel', 'Cancelled')
            # kanban_state: ('normal', 'In Progress'), ('done', 'Completed'), ('blocked', 'Blocked')
            if  not det:
                warning = False
            else:   
                warning = ( det.kanban_state == 'blocked') or ((det.state == 'open') and (det.date_end <= date.today()))
            employee.disponibilite_warning = warning

            # Mise à jour automatique du poste administratif
            if (not warning) and disponibilite_position and det:
                # Si mise en disponibilité actif et valide
                employee.position_id = disponibilite_position.id   # affectation correcte


    def _compute_disponibilites_count(self):
        # read_group as sudo, since disponibilite count is displayed on form view
        disponibilite_histories = self.env['hr.disponibilite.history'].sudo().search([('employee_id', 'in', self.ids)])
        for employee in self:
            disponibilite_history = disponibilite_histories.filtered(lambda ch: ch.employee_id == employee)
            employee.disponibilites_count = disponibilite_history.disponibilite_count

    def _get_disponibilites(self, date_from, date_to, states=['open'], kanban_state=False):
        """
        Returns the disponibilites of the employee between date_from and date_to
        """
        state_domain = [('state', 'in', states)]
        if kanban_state:
            state_domain = expression.AND([state_domain, [('kanban_state', 'in', kanban_state)]])

        return self.env['hr.disponibilite'].search(
            expression.AND([[('employee_id', 'in', self.ids)],
            state_domain,
            [('date_start', '<=', date_to),
                '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_from)]]))

    def _get_incoming_disponibilites(self, date_from, date_to):
        return self._get_disponibilites(date_from, date_to, states=['draft'], kanban_state=['done'])
    @api.model
    def _get_all_disponibilites(self, date_from, date_to, states=['open']):
        """
        Returns the disponibilites of all employees between date_from and date_to
        """
        return self.search(['|', ('active', '=', True), ('active', '=', False)])._get_disponibilites(date_from, date_to, states=states)

    def write(self, vals):
        res = super().write(vals)
        
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_open_disponibilite(self):
        if any(disponibilite.state == 'open' for disponibilite in self.disponibilite_ids):
            raise UserError(_('You cannot delete an employee with a running disponibilite.'))

    def action_open_disponibilite(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_disponibilite.action_hr_disponibilite')
        action['views'] = [(False, 'form')]
        if not self.disponibilite_ids:
            action['context'] = {
                'default_employee_id': self.id,
                'from_action_open_disponibilite': True,
            }
            action['target'] = 'current'
            return action

        target_disponibilite = self.disponibilite_id
        if target_disponibilite:
            action['res_id'] = target_disponibilite.id
            return action

        target_disponibilite = self.disponibilite_ids.filtered(lambda c: c.state == 'draft')
        if target_disponibilite:
            action['res_id'] = target_disponibilite[0].id
            return action

        action['res_id'] = self.disponibilite_ids[0].id
        return action
