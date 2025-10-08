# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import threading

from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.osv import expression

import logging
_logger = logging.getLogger(__name__)


class Detachement(models.Model):
    _name = 'hr.detachement'
    _description = 'Detachement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _mail_post_access = 'read'

    name = fields.Char('Detachement Reference', required=True)
    active = fields.Boolean(default=True)
    structure_type_id = fields.Many2one('hr.payroll.structure.type', string="Salary Structure Type", compute="_compute_structure_type_id", readonly=False, store=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", index=True)
    active_employee = fields.Boolean(related="employee_id.active", string="Active Employee")
    department_id = fields.Many2one('hr.department', compute='_compute_employee_detachement', store=True, readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", string="Department")
    job_id = fields.Many2one('hr.job', compute='_compute_employee_detachement', store=True, readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", string='Job Position')
    date_start = fields.Date('Start Date', required=True, default=fields.Date.today, tracking=True, index=True)
    date_end = fields.Date('End Date', tracking=True,
        help="End date of the detachement (if it's a fixed-term detachement).")
    trial_date_end = fields.Date('End of Trial Period',
        help="End date of the trial period (if there is one).")
    resource_calendar_id = fields.Many2one(
        'resource.calendar', 'Working Schedule', compute='_compute_employee_detachement', store=True, readonly=False,
        default=lambda self: self.env.company.resource_calendar_id.id, copy=False, index=True, tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    wage = fields.Monetary('Wage', required=True, tracking=True, help="Employee's monthly gross wage.", aggregator="avg")
    detachement_wage = fields.Monetary('Detachement Wage', compute='_compute_detachement_wage')
    notes = fields.Html('Notes')
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', group_expand=True, copy=False,
        tracking=True, help='Status of the detachement', default='draft')
    company_id = fields.Many2one('res.company', compute='_compute_employee_detachement', store=True, readonly=False,
        default=lambda self: self.env.company, required=True)
    company_country_id = fields.Many2one('res.country', string="Company country", related='company_id.country_id', readonly=True)
    country_code = fields.Char(related='company_country_id.code', depends=['company_country_id'], readonly=True)
    detachements_count = fields.Integer(related='employee_id.detachements_count', groups="hr_detachement.group_hr_detachement_employee_manager")

    """
        kanban_state:
            * draft + green = "Incoming" state (will be set as Open once the detachement has started)
            * open + red = "Pending" state (will be set as Closed once the detachement has ended)
            * red = Shows a warning on the employees kanban view
    """
    kanban_state = fields.Selection([
        ('normal', 'Ongoing'),
        ('done', 'Ready'),
        ('blocked', 'Warning')
    ], string='Kanban State', default='normal', tracking=True, copy=False)
    currency_id = fields.Many2one(string="Currency", related='company_id.currency_id', readonly=True)
    permit_no = fields.Char('Work Permit No', related="employee_id.permit_no", readonly=False)
    visa_no = fields.Char('Visa No', related="employee_id.visa_no", readonly=False)

    def _get_hr_responsible_domain(self):
        return "[('share', '=', False), ('company_ids', 'in', company_id), ('groups_id', 'in', %s)]" % self.env.ref('hr.group_hr_user').id

    hr_responsible_id = fields.Many2one('res.users', 'HR Responsible', tracking=True,
        help='Person responsible for validating the employee\'s detachements.', domain=_get_hr_responsible_domain)
    calendar_mismatch = fields.Boolean(compute='_compute_calendar_mismatch', compute_sudo=True)
    first_detachement_date = fields.Date(related='employee_id.first_detachement_date')

    @api.depends('employee_id.resource_calendar_id', 'resource_calendar_id')
    def _compute_calendar_mismatch(self):
        for detachement in self:
            detachement.calendar_mismatch = detachement.resource_calendar_id != detachement.employee_id.resource_calendar_id

    def _get_salary_costs_factor(self):
        self.ensure_one()
        return 12.0

    @api.depends('employee_id')
    def _compute_employee_detachement(self):
        for detachement in self.filtered('employee_id'):
            detachement.job_id = detachement.employee_id.job_id
            detachement.department_id = detachement.employee_id.department_id
            detachement.resource_calendar_id = detachement.employee_id.resource_calendar_id
            detachement.company_id = detachement.employee_id.company_id

    @api.depends('company_id')
    def _compute_structure_type_id(self):

        default_structure_by_country = {}

        def _default_salary_structure(country_id):
            default_structure = default_structure_by_country.get(country_id)
            if default_structure is None:
                default_structure = default_structure_by_country[country_id] = (
                    self.env['hr.payroll.structure.type'].search([('country_id', '=', country_id)], limit=1)
                    or self.env['hr.payroll.structure.type'].search([('country_id', '=', False)], limit=1)
                )
            return default_structure

        for detachement in self:
            if not detachement.structure_type_id or (detachement.structure_type_id.country_id and detachement.structure_type_id.country_id != detachement.company_id.country_id):
                detachement.structure_type_id = _default_salary_structure(detachement.company_id.country_id.id)

    @api.onchange('structure_type_id')
    def _onchange_structure_type_id(self):
        default_calendar = self.structure_type_id.default_resource_calendar_id
        if default_calendar and default_calendar.company_id == self.company_id:
            # If the form was opened from the action_open_detachement action,
            # suggest current employee's calendar for the new detachement instead of the default_calendar.
            if self.env.context.get('from_action_open_detachement'):
                return
            self.resource_calendar_id = default_calendar

    @api.constrains('employee_id', 'state', 'kanban_state', 'date_start', 'date_end')
    def _check_current_detachement(self):
        """ Two detachements in state [incoming | open | close] cannot overlap """
        for detachement in self.filtered(lambda c: (c.state not in ['draft', 'cancel'] or c.state == 'draft' and c.kanban_state == 'done') and c.employee_id):
            domain = [
                ('id', '!=', detachement.id),
                ('employee_id', '=', detachement.employee_id.id),
                ('company_id', '=', detachement.company_id.id),
                '|',
                    ('state', 'in', ['open', 'close']),
                    '&',
                        ('state', '=', 'draft'),
                        ('kanban_state', '=', 'done') # replaces incoming
            ]

            if not detachement.date_end:
                start_domain = []
                end_domain = ['|', ('date_end', '>=', detachement.date_start), ('date_end', '=', False)]
            else:
                start_domain = [('date_start', '<=', detachement.date_end)]
                end_domain = ['|', ('date_end', '>', detachement.date_start), ('date_end', '=', False)]

            domain = expression.AND([domain, start_domain, end_domain])
            if self.search_count(domain):
                raise ValidationError(
                    _(
                        'An employee can only have one detachement at the same time. (Excluding Draft and Cancelled detachements).\n\nEmployee: %(employee_name)s',
                        employee_name=detachement.employee_id.name
                    )
                )

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for detachement in self:
            if detachement.date_end and detachement.date_start > detachement.date_end:
                raise ValidationError(_(
                    'Detachement %(detachement)s: start date (%(start)s) must be earlier than detachement end date (%(end)s).',
                    detachement=detachement.name, start=detachement.date_start, end=detachement.date_end,
                ))

    @api.model
    def update_state(self):
        from_cron = 'from_cron' in self.env.context
        companies = self.env['res.company'].search([])
        detachements = self.env['hr.detachement']
        work_permit_detachements = self.env['hr.detachement']
        for company in companies:
            detachements += self.search([
                ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'), ('company_id', '=', company.id),
                '&',
                ('date_end', '<=', fields.date.today() + relativedelta(days=company.detachement_expiration_notice_period)),
                ('date_end', '>=', fields.date.today() + relativedelta(days=1)),
            ])

            work_permit_detachements += self.search([
                ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'), ('company_id', '=', company.id),
                '&',
                ('employee_id.work_permit_expiration_date', '<=', fields.date.today() + relativedelta(days=company.work_permit_expiration_notice_period)),
                ('employee_id.work_permit_expiration_date', '>=', fields.date.today() + relativedelta(days=1)),
            ])

        for detachement in detachements:
            detachement.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo', detachement.date_end,
                _("The detachement of %s is about to expire.", detachement.employee_id.name),
                user_id=detachement.hr_responsible_id.id or self.env.uid)
            detachement.message_post(
                body=_(
                    "According to the detachement's end date, this detachement has been put in red on the %s. Please advise and correct.",
                    fields.Date.today()
                )
            )

        for detachement in work_permit_detachements:
            detachement.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo', detachement.date_end,
                _("The work permit of %s is about to expire.", detachement.employee_id.name),
                user_id=detachement.hr_responsible_id.id or self.env.uid)
            detachement.message_post(
                body=_(
                    "According to Employee's Working Permit Expiration Date, this detachement has been put in red on the %s. Please advise and correct.",
                    fields.Date.today()
                )
            )

        if detachements:
            detachements._safe_write_for_cron({'kanban_state': 'blocked'}, from_cron)
        if work_permit_detachements:
            work_permit_detachements._safe_write_for_cron({'kanban_state': 'blocked'}, from_cron)

        detachements_to_close = self.search([
            ('state', '=', 'open'),
            '|',
            ('date_end', '<=', fields.Date.to_string(date.today())),
            ('employee_id.work_permit_expiration_date', '<=', fields.Date.to_string(date.today())),
        ])

        if detachements_to_close:
            detachements_to_close._safe_write_for_cron({'state': 'close'}, from_cron)

        detachements_to_open = self.search([('state', '=', 'draft'), ('kanban_state', '=', 'done'), ('date_start', '<=', fields.Date.to_string(date.today())),])

        if detachements_to_open:
            detachements_to_open._safe_write_for_cron({'state': 'open'}, from_cron)

        detachement_ids = self.search([('date_end', '=', False), ('state', '=', 'close'), ('employee_id', '!=', False)])
        # Ensure all closed detachement followed by a new detachement have a end date.
        # If closed detachement has no closed date, the work entries will be generated for an unlimited period.
        for detachement in detachement_ids:
            next_detachement = self.search([
                ('employee_id', '=', detachement.employee_id.id),
                ('state', 'not in', ['cancel', 'draft']),
                ('date_start', '>', detachement.date_start)
            ], order="date_start asc", limit=1)
            if next_detachement:
                detachement._safe_write_for_cron({'date_end': next_detachement.date_start - relativedelta(days=1)}, from_cron)
                continue
            next_detachement = self.search([
                ('employee_id', '=', detachement.employee_id.id),
                ('date_start', '>', detachement.date_start)
            ], order="date_start asc", limit=1)
            if next_detachement:
                detachement._safe_write_for_cron({'date_end': next_detachement.date_start - relativedelta(days=1)}, from_cron)

        return True

    def _safe_write_for_cron(self, vals, from_cron=False):
        if from_cron:
            auto_commit = not getattr(threading.current_thread(), 'testing', False)
            for detachement in self:
                try:
                    with self.env.cr.savepoint():
                        detachement.write(vals)
                except ValidationError as e:
                    _logger.warning(e)
                else:
                    if auto_commit:
                        self.env.cr.commit()
        else:
            self.write(vals)

    def _get_employee_vals_to_update(self):
        self.ensure_one()
        vals = {'detachement_id': self.id}
        if self.job_id and self.job_id != self.employee_id.job_id:
            vals['job_id'] = self.job_id.id
        if self.department_id:
            vals['department_id'] = self.department_id.id
        return vals

    def _assign_open_detachement(self):
        for detachement in self:
            vals = detachement._get_employee_vals_to_update()
            detachement.employee_id.sudo().write(vals)

    @api.depends('wage')
    def _compute_detachement_wage(self):
        for detachement in self:
            detachement.detachement_wage = detachement._get_detachement_wage()

    def _get_detachement_wage(self):
        if not self:
            return 0
        self.ensure_one()
        return self[self._get_detachement_wage_field()]

    def _get_detachement_wage_field(self):
        self.ensure_one()
        return 'wage'

    def _is_fully_flexible(self):
        """ return True if detachement has a fully flexible working calendar """
        self.ensure_one()
        return not self.resource_calendar_id

    def write(self, vals):
        old_state = {c.id: c.state for c in self}
        res = super(Detachement, self).write(vals)
        new_state = {c.id: c.state for c in self}
        if vals.get('state') == 'open':
            self._assign_open_detachement()
        today = fields.Date.today()
        for detachement in self:
            if detachement == detachement.sudo().employee_id.detachement_id \
                and old_state[detachement.id] == 'open' \
                and new_state[detachement.id] != 'open':
                running_detachement = self.env['hr.detachement'].search([
                    ('employee_id', '=', detachement.employee_id.id),
                    ('company_id', '=', detachement.company_id.id),
                    ('state', '=', 'open'),
                ]).filtered(lambda c: c.date_start <= today and (not c.date_end or c.date_end >= today))
                if running_detachement:
                    detachement.employee_id.sudo().detachement_id = running_detachement[0]
        if vals.get('state') == 'close':
            for detachement in self.filtered(lambda c: not c.date_end):
                detachement.date_end = max(date.today(), detachement.date_start)
        date_end = vals.get('date_end')
        if self.env.context.get('close_detachement', True) and date_end and fields.Date.from_string(date_end) < fields.Date.context_today(self):
            for detachement in self.filtered(lambda c: c.state == 'open'):
                detachement.state = 'close'

        if 'resource_calendar_id' in vals:
            calendar = vals['resource_calendar_id']
            self.filtered(
                lambda c: c.state == 'open' or (c.state == 'draft' and c.kanban_state == 'done' and c.employee_id.detachements_count == 1)
            ).employee_id.resource_calendar_id = calendar

        if 'state' in vals and 'kanban_state' not in vals:
            self.write({'kanban_state': 'normal'})

        return res

    @api.model_create_multi
    def create(self, vals_list):
        detachements = super().create(vals_list)
        detachements.filtered(lambda c: c.state == 'open')._assign_open_detachement()
        open_detachements = detachements.filtered(
            lambda c: c.state == 'open' or (c.state == 'draft' and c.kanban_state == 'done' and c.employee_id.detachements_count == 1)
        )
        # sync detachement calendar -> calendar employee
        for detachement in open_detachements.filtered(lambda c: c.employee_id):
            detachement.employee_id.resource_calendar_id = detachement.resource_calendar_id
        return detachements

    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'open' and 'kanban_state' in init_values and self.kanban_state == 'blocked':
            return self.env.ref('hr_detachement.mt_detachement_pending')
        elif 'state' in init_values and self.state == 'close':
            return self.env.ref('hr_detachement.mt_detachement_close')
        return super(Detachement, self)._track_subtype(init_values)

    def _is_struct_from_country(self, country_code):
        self.ensure_one()
        self_sudo = self.sudo()
        return self_sudo.structure_type_id and self_sudo.structure_type_id.country_id.code == country_code

    def action_open_detachement_form(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hr_detachement.action_hr_detachement')
        action.update({
            'view_mode': 'form',
            'view_id': self.env.ref('hr_detachement.hr_detachement_view_form').id,
            'views': [(self.env.ref('hr_detachement.hr_detachement_view_form').id, 'form')],
            'res_id': self.id,
        })
        return action

    def action_open_detachement_history(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_detachement.hr_detachement_history_view_form_action')
        action['res_id'] = self.employee_id.id
        return action

    def action_open_detachement_list(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_detachement.action_hr_detachement')
        action.update({'domain': [('employee_id', '=', self.employee_id.id)],
                      'views':  [[False, 'list'], [False, 'kanban'], [False, 'activity'], [False, 'form']],
                       'context': {'default_employee_id': self.employee_id.id}})
        return action
