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
    vehicle = fields.Char(string='Company Vehicle', groups="hr.group_hr_user")
    detachement_ids = fields.One2many('hr.detachement', 'employee_id', string='Employee Detachements', groups="hr.group_hr_user")
    detachement_id = fields.Many2one(
        'hr.detachement', string='Current Detachement', groups="hr.group_hr_user",
        domain="[('company_id', '=', company_id), ('employee_id', '=', id)]", help='Current detachement of the employee', copy=False)
    calendar_mismatch = fields.Boolean(related='detachement_id.calendar_mismatch', groups="base.group_system,hr.group_hr_user")
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
        for employee in self:
            employee.detachement_warning = not employee.detachement_id or employee.detachement_id.kanban_state == 'blocked' or employee.detachement_id.state != 'open'

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

    def _get_calendars(self, date_from=None):
        res = super()._get_calendars(date_from=date_from)
        if not date_from:
            return res
        detachements = self.env['hr.detachement'].sudo().search([
            '|',
                ('state', 'in', ['open', 'close']),
                '&',
                    ('state', '=', 'draft'),
                    ('kanban_state', '=', 'done'),
            ('employee_id', 'in', self.ids),
            ('date_start', '<=', date_from),
            '|',
                ('date_end', '=', False),
                ('date_end', '>=', date_from)
        ])
        detachements_by_employee = defaultdict(lambda: self.env['hr.detachement'])
        for detachement in detachements:
            detachements_by_employee[detachement.employee_id] += detachement
        for employee in self:
            employee_detachements = detachements_by_employee[employee.id]
            if employee_detachements:
                res[employee.id] = detachements[0].resource_calendar_id.sudo(False)
        return res

    def _get_calendar_periods(self, start, stop):
        """
        :param datetime start: the start of the period
        :param datetime stop: the stop of the period
        """
        calendar_periods_by_employee = defaultdict(list)
        detachements_by_employee = self.env['hr.detachement'].sudo()._read_group(domain=[
            '|',
                ('state', 'in', ['open', 'close']),
                '&',
                    ('state', '=', 'draft'),
                    ('kanban_state', '=', 'done'),
            ('date_start', '<=', stop),
            '|',
                ('date_end', '=', False),
                ('date_end', '>=', start),
            ('employee_id', 'in', self.ids),
        ], groupby=['employee_id'], aggregates=['id:recordset'])
        for employee, detachements in detachements_by_employee:
            for detachement in detachements:
                # if employee is under fully flexible detachement, use timezone of the employee
                calendar_tz = timezone(detachement.resource_calendar_id.tz) if detachement.resource_calendar_id else timezone(employee.resource_id.tz)
                utc = timezone('UTC')
                date_start = datetime.combine(
                    detachement.date_start,
                    time(0, 0, 0)
                ).replace(tzinfo=calendar_tz).astimezone(utc)
                if detachement.date_end:
                    date_end = datetime.combine(
                        detachement.date_end + relativedelta(days=1),
                        time(0, 0, 0)
                    ).replace(tzinfo=calendar_tz).astimezone(utc)
                else:
                    date_end = stop
                calendar_periods_by_employee[employee].append(
                    (max(date_start, start), min(date_end, stop), detachement.resource_calendar_id)
                )
        return calendar_periods_by_employee

    @api.model
    def _get_all_detachements(self, date_from, date_to, states=['open']):
        """
        Returns the detachements of all employees between date_from and date_to
        """
        return self.search(['|', ('active', '=', True), ('active', '=', False)])._get_detachements(date_from, date_to, states=states)

    def _get_unusual_days(self, date_from, date_to=None):
        employee_detachements = self.env['hr.detachement'].sudo().search([
            ('state', '!=', 'cancel'),
            ('employee_id', '=', self.id),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
        ])
        if not employee_detachements:
            return super()._get_unusual_days(date_from, date_to)
        unusual_days = {}
        date_from_date = datetime.strptime(date_from, '%Y-%m-%d %H:%M:%S').date()
        date_to_date = datetime.strptime(date_to, '%Y-%m-%d %H:%M:%S').date() if date_to else None
        for detachement in employee_detachements:
            tmp_date_from = max(date_from_date, detachement.date_start)
            tmp_date_to = min(date_to_date, detachement.date_end) if detachement.date_end else date_to_date
            unusual_days.update(detachement.resource_calendar_id.sudo(False)._get_unusual_days(
                datetime.combine(fields.Date.from_string(tmp_date_from), time.min).replace(tzinfo=UTC),
                datetime.combine(fields.Date.from_string(tmp_date_to), time.max).replace(tzinfo=UTC),
                self.company_id,
            ))
        return unusual_days

    def _employee_attendance_intervals(self, start, stop, lunch=False):
        self.ensure_one()
        if not lunch:
            return self._get_expected_attendances(start, stop)
        else:
            valid_detachements = self.sudo()._get_detachements(start, stop, states=['open', 'close'])
            if not valid_detachements:
                return super()._employee_attendance_intervals(start, stop, lunch)
            employee_tz = timezone(self.tz) if self.tz else None
            duration_data = Intervals()
            for detachement in valid_detachements:
                detachement_start = datetime.combine(detachement.date_start, time.min, employee_tz)
                detachement_end = datetime.combine(detachement.date_end or date.max, time.max, employee_tz)
                calendar = detachement.resource_calendar_id or detachement.company_id.resource_calendar_id
                lunch_intervals = calendar._attendance_intervals_batch(
                    max(start, detachement_start),
                    min(stop, detachement_end),
                    resources=self.resource_id,
                    lunch=True)[self.resource_id.id]
                duration_data = duration_data | lunch_intervals
            return duration_data

    def _get_expected_attendances(self, date_from, date_to):
        self.ensure_one()
        valid_detachements = self.sudo()._get_detachements(date_from, date_to, states=['open', 'close'])
        if not valid_detachements:
            return super()._get_expected_attendances(date_from, date_to)
        employee_tz = timezone(self.tz) if self.tz else None
        duration_data = Intervals()
        for detachement in valid_detachements:
            detachement_start = datetime.combine(detachement.date_start, time.min, employee_tz)
            detachement_end = datetime.combine(detachement.date_end or date.max, time.max, employee_tz)
            calendar = detachement.resource_calendar_id or detachement.company_id.resource_calendar_id
            detachement_intervals = calendar._work_intervals_batch(
                                    max(date_from, detachement_start),
                                    min(date_to, detachement_end),
                                    tz=employee_tz,
                                    resources=self.resource_id,
                                    compute_leaves=True)[self.resource_id.id]
            duration_data = duration_data | detachement_intervals
        return duration_data

    def _get_calendar_attendances(self, date_from, date_to):
        self.ensure_one()
        valid_detachements = self.sudo()._get_detachements(date_from, date_to, states=['open', 'close'])
        if not valid_detachements:
            return super()._get_calendar_attendances(date_from, date_to)
        employee_tz = timezone(self.tz) if self.tz else None
        duration_data = {'days': 0, 'hours': 0}
        for detachement in valid_detachements:
            detachement_start = datetime.combine(detachement.date_start, time.min, employee_tz)
            detachement_end = datetime.combine(detachement.date_end or date.max, time.max, employee_tz)
            calendar = detachement.resource_calendar_id or detachement.company_id.resource_calendar_id
            detachement_duration_data = calendar\
                .with_context(employee_timezone=employee_tz)\
                .get_work_duration_data(
                    max(date_from, detachement_start),
                    min(date_to, detachement_end),
                    domain=[('company_id', 'in', [False, detachement.company_id.id])])
            duration_data['days'] += detachement_duration_data['days']
            duration_data['hours'] += detachement_duration_data['hours']
        return duration_data

    def write(self, vals):
        res = super().write(vals)
        if vals.get('detachement_id'):
            for employee in self:
                employee.resource_calendar_id.transfer_leaves_to(employee.detachement_id.resource_calendar_id, employee.resource_id)
                employee.resource_calendar_id = employee.detachement_id.resource_calendar_id
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
                # display current resource_calendar_id as the default one if it exists (if False, fully flexible calendar)
                'default_resource_calendar_id': self.resource_calendar_id.id or False,
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
