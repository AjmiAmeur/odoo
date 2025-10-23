# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import threading

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.osv import expression

import logging
_logger = logging.getLogger(__name__)


class Disponibilite(models.Model):
    _name = 'hr.disponibilite'
    _description = 'Mise en disponibilité des employés'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _mail_post_access = 'read'

    name = fields.Char(
        string='Référence de la Mise en disponibilité',
        compute='_compute_name',
        store=True,
        readonly=False,
    )
    active = fields.Boolean(default=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", index=True)
    active_employee = fields.Boolean(related="employee_id.active", string="Active Employee")
    date_start = fields.Date('Date de début de la mise en disponibilité', required=True, default=fields.Date.today, tracking=True, index=True)
    date_end = fields.Date('Date de fin de la mise en disponibilité', tracking=True,
        help="Date d’expiration de la mise en disponibilité.")
    duration_days = fields.Integer(compute="_compute_duration", store=False)
    duration_months = fields.Integer(compute="_compute_duration", store=False)
    duration_years = fields.Integer(compute="_compute_duration", store=False)
    duration_display = fields.Char('Période de mise en disponibilité',compute="_compute_duration", store=False)
    motif_id = fields.Many2one('hr.motif.disponibilite', string='Motif de mise en disponibilité', tracking=True,
        help='Motif de la mise en disponibilité.')    
   
    notes = fields.Html('Notes')
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', group_expand=True, copy=False,
        tracking=True, help='Status of the disponibilite', default='draft')
    company_id = fields.Many2one('res.company', compute='_compute_employee_disponibilite', store=True, readonly=False,
        default=lambda self: self.env.company, required=True)
    company_country_id = fields.Many2one('res.country', string="Company country", related='company_id.country_id', readonly=True)
    country_code = fields.Char(related='company_country_id.code', depends=['company_country_id'], readonly=True)

    disponibilites_count = fields.Integer(related='employee_id.disponibilites_count', groups="hr_disponibilite.group_hr_disponibilite_employee_manager")

   

    """
        kanban_state:
            * draft + green = "Incoming" state (will be set as Open once the disponibilite has started)
            * open + red = "Pending" state (will be set as Closed once the disponibilite has ended)
            * red = Shows a warning on the employees kanban view
    """
    kanban_state = fields.Selection([
        ('normal', 'Ongoing'),
        ('done', 'Ready'),
        ('blocked', 'Warning')
    ], string='Kanban State', default='normal', tracking=True, copy=False)

    def _get_hr_responsible_domain(self):
        return "[('share', '=', False), ('company_ids', 'in', company_id), ('groups_id', 'in', %s)]" % self.env.ref('hr.group_hr_user').id

    hr_responsible_id = fields.Many2one('res.users', 'HR Responsible', tracking=True,
        help='Person responsible for validating the employee\'s disponibilites.', domain=_get_hr_responsible_domain)
    first_disponibilite_date = fields.Date(related='employee_id.first_disponibilite_date')
    @api.depends('employee_id.identification_id', 'date_start')
    def _compute_name(self):
        """Génère automatiquement le nom du détachement."""
        for rec in self:
            if rec.employee_id and rec.date_start:
                rec.name = f"M.D./{rec.employee_id.identification_id} - {rec.date_start.strftime('%d/%m/%Y')}"
            elif rec.employee_id:
                rec.name = "M.D./"+rec.employee_id.identification_id
            else:
                rec.name = False
    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            start = rec.date_start
            end = rec.date_end or date.today()

            # Si date_start vide ou date_end avant date_start → durée à 0
            if not start or end < start:
                rec.duration_days = 0
                rec.duration_months = 0
                rec.duration_years = 0
                rec.duration_display = "0 jour"
                continue

            delta = relativedelta(end + timedelta(days=1), start)

            rec.duration_years = delta.years
            rec.duration_months = delta.months
            rec.duration_days = delta.days

            # Construction du texte lisible
            parts = []
            if delta.years:
                parts.append(f"{delta.years} an{'s' if delta.years > 1 else ''}")
            if delta.months:
                parts.append(f"{delta.months} mois")
            if delta.days:
                parts.append(f"{delta.days} jour{'s' if delta.days > 1 else ''}")

            rec.duration_display = " et ".join(parts) if parts else "0 jour"


 
   
    

    @api.depends('employee_id')
    def _compute_employee_disponibilite(self):
        for disponibilite in self.filtered('employee_id'):
            disponibilite.company_id = disponibilite.employee_id.company_id

    
    

    @api.constrains('employee_id', 'state', 'kanban_state', 'date_start', 'date_end')
    def _check_current_disponibilite(self):
        """ Two disponibilites in state [incoming | open | close] cannot overlap """
        for disponibilite in self.filtered(lambda c: (c.state not in ['draft', 'cancel'] or c.state == 'draft' and c.kanban_state == 'done') and c.employee_id):
            domain = [
                ('id', '!=', disponibilite.id),
                ('employee_id', '=', disponibilite.employee_id.id),
                ('company_id', '=', disponibilite.company_id.id),
                '|',
                    ('state', 'in', ['open', 'close']),
                    '&',
                        ('state', '=', 'draft'),
                        ('kanban_state', '=', 'done') # replaces incoming
            ]

            if not disponibilite.date_end:
                start_domain = []
                end_domain = ['|', ('date_end', '>=', disponibilite.date_start), ('date_end', '=', False)]
            else:
                start_domain = [('date_start', '<=', disponibilite.date_end)]
                end_domain = ['|', ('date_end', '>', disponibilite.date_start), ('date_end', '=', False)]

            domain = expression.AND([domain, start_domain, end_domain])
            if self.search_count(domain):
                raise ValidationError(
                    _(
                        "Un employé ne peut avoir qu'une seule mise en disponibilité à la fois (à l’exception de celles à l’état Brouillon ou Annulée).\n\nEmployé : %(employee_name)s",
                            employee_name=disponibilite.employee_id.name
                    )
                )

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for disponibilite in self:
            if disponibilite.date_end and disponibilite.date_start > disponibilite.date_end:
                raise ValidationError(_(
                    "Disponibilité %(disponibilite)s : la date de début (%(start)s) doit être antérieure à la date de fin (%(end)s).",
                    disponibilite=disponibilite.name, start=disponibilite.date_start, end=disponibilite.date_end,
                ))

    @api.model
    def update_state(self):
        from_cron = 'from_cron' in self.env.context
        companies = self.env['res.company'].search([])
        disponibilites = self.env['hr.disponibilite']
        work_permit_disponibilites = self.env['hr.disponibilite']
        for company in companies:
            disponibilites += self.search([
                ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'), ('company_id', '=', company.id),
                '&',
                ('date_end', '<=', fields.date.today() + relativedelta(days=company.disponibilite_expiration_notice_period)),
                ('date_end', '>=', fields.date.today() + relativedelta(days=1)),
            ])

            work_permit_disponibilites += self.search([
                ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'), ('company_id', '=', company.id),
                '&',
                ('employee_id.work_permit_expiration_date', '<=', fields.date.today() + relativedelta(days=company.work_permit_expiration_notice_period)),
                ('employee_id.work_permit_expiration_date', '>=', fields.date.today() + relativedelta(days=1)),
            ])

        for disponibilite in disponibilites:
            disponibilite.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo', disponibilite.date_end,
                _("The disponibilite of %s is about to expire.", disponibilite.employee_id.name),
                user_id=disponibilite.hr_responsible_id.id or self.env.uid)
            disponibilite.message_post(
                body=_(
                    "Selon la date de fin de la disponibilité, cette disponibilité a été mise en rouge sur le %s. Veuillez vérifier et corriger.",
                    fields.Date.today()
                )
            )

        for disponibilite in work_permit_disponibilites:
            disponibilite.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo', disponibilite.date_end,
                _("The work permit of %s is about to expire.", disponibilite.employee_id.name),
                user_id=disponibilite.hr_responsible_id.id or self.env.uid)
            disponibilite.message_post(
                body=_(
                    "Selon la date d’expiration du permis de travail de l’employé, cette disponibilité a été mise en rouge le %s. Veuillez vérifier et corriger.",
                    fields.Date.today()
                )
            )

        if disponibilites:
            disponibilites._safe_write_for_cron({'kanban_state': 'blocked'}, from_cron)
        if work_permit_disponibilites:
            work_permit_disponibilites._safe_write_for_cron({'kanban_state': 'blocked'}, from_cron)

        disponibilites_to_close = self.search([
            ('state', '=', 'open'),
            '|',
            ('date_end', '<=', fields.Date.to_string(date.today())),
            ('employee_id.work_permit_expiration_date', '<=', fields.Date.to_string(date.today())),
        ])

        if disponibilites_to_close:
            disponibilites_to_close._safe_write_for_cron({'state': 'close'}, from_cron)

        disponibilites_to_open = self.search([('state', '=', 'draft'), ('kanban_state', '=', 'done'), ('date_start', '<=', fields.Date.to_string(date.today())),])

        if disponibilites_to_open:
            disponibilites_to_open._safe_write_for_cron({'state': 'open'}, from_cron)

        disponibilite_ids = self.search([('date_end', '=', False), ('state', '=', 'close'), ('employee_id', '!=', False)])
        # Ensure all closed disponibilite followed by a new disponibilite have a end date.
        # If closed disponibilite has no closed date, the work entries will be generated for an unlimited period.
        for disponibilite in disponibilite_ids:
            next_disponibilite = self.search([
                ('employee_id', '=', disponibilite.employee_id.id),
                ('state', 'not in', ['cancel', 'draft']),
                ('date_start', '>', disponibilite.date_start)
            ], order="date_start asc", limit=1)
            if next_disponibilite:
                disponibilite._safe_write_for_cron({'date_end': next_disponibilite.date_start - relativedelta(days=1)}, from_cron)
                continue
            next_disponibilite = self.search([
                ('employee_id', '=', disponibilite.employee_id.id),
                ('date_start', '>', disponibilite.date_start)
            ], order="date_start asc", limit=1)
            if next_disponibilite:
                disponibilite._safe_write_for_cron({'date_end': next_disponibilite.date_start - relativedelta(days=1)}, from_cron)

        return True

    def _safe_write_for_cron(self, vals, from_cron=False):
        if from_cron:
            auto_commit = not getattr(threading.current_thread(), 'testing', False)
            for disponibilite in self:
                try:
                    with self.env.cr.savepoint():
                        disponibilite.write(vals)
                except ValidationError as e:
                    _logger.warning(e)
                else:
                    if auto_commit:
                        self.env.cr.commit()
        else:
            self.write(vals)

    def _get_employee_vals_to_update(self):
        self.ensure_one()
        vals = {'disponibilite_id': self.id}
        return vals

    def _assign_open_disponibilite(self):
        for disponibilite in self:
            vals = disponibilite._get_employee_vals_to_update()
            disponibilite.employee_id.sudo().write(vals)

    
  


    

    def write(self, vals):
        old_state = {c.id: c.state for c in self}
        res = super(Disponibilite, self).write(vals)
        new_state = {c.id: c.state for c in self}
        if vals.get('state') == 'open':
            self._assign_open_disponibilite()
        today = fields.Date.today()
        for disponibilite in self:
            if disponibilite == disponibilite.sudo().employee_id.disponibilite_id \
                and old_state[disponibilite.id] == 'open' \
                and new_state[disponibilite.id] != 'open':
                running_disponibilite = self.env['hr.disponibilite'].search([
                    ('employee_id', '=', disponibilite.employee_id.id),
                    ('company_id', '=', disponibilite.company_id.id),
                    ('state', '=', 'open'),
                ]).filtered(lambda c: c.date_start <= today and (not c.date_end or c.date_end >= today))
                if running_disponibilite:
                    disponibilite.employee_id.sudo().disponibilite_id = running_disponibilite[0]
        if vals.get('state') == 'close':
            for disponibilite in self.filtered(lambda c: not c.date_end):
                disponibilite.date_end = max(date.today(), disponibilite.date_start)
        date_end = vals.get('date_end')
        if self.env.context.get('close_disponibilite', True) and date_end and fields.Date.from_string(date_end) < fields.Date.context_today(self):
            for disponibilite in self.filtered(lambda c: c.state == 'open'):
                disponibilite.state = 'close'

        
        if 'state' in vals and 'kanban_state' not in vals:
            self.write({'kanban_state': 'normal'})

        return res

    @api.model_create_multi
    def create(self, vals_list):
        disponibilites = super().create(vals_list)
        disponibilites.filtered(lambda c: c.state == 'open')._assign_open_disponibilite()
        open_disponibilites = disponibilites.filtered(
            lambda c: c.state == 'open' or (c.state == 'draft' and c.kanban_state == 'done' and c.employee_id.disponibilites_count == 1)
        )
        # sync disponibilite calendar -> calendar employee
        
        return disponibilites

    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'open' and 'kanban_state' in init_values and self.kanban_state == 'blocked':
            return self.env.ref('hr_disponibilite.mt_disponibilite_pending')
        elif 'state' in init_values and self.state == 'close':
            return self.env.ref('hr_disponibilite.mt_disponibilite_close')
        return super(Disponibilite, self)._track_subtype(init_values)

   

    def action_open_disponibilite_form(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hr_disponibilite.action_hr_disponibilite')
        action.update({
            'view_mode': 'form',
            'view_id': self.env.ref('hr_disponibilite.hr_disponibilite_view_form').id,
            'views': [(self.env.ref('hr_disponibilite.hr_disponibilite_view_form').id, 'form')],
            'res_id': self.id,
        })
        return action

    def action_open_disponibilite_history(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_disponibilite.hr_disponibilite_history_view_form_action')
        action['res_id'] = self.employee_id.id
        return action

    def action_open_disponibilite_list(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('hr_disponibilite.action_hr_disponibilite')
        action.update({'domain': [('employee_id', '=', self.employee_id.id)],
                      'views':  [[False, 'list'], [False, 'kanban'], [False, 'activity'], [False, 'form']],
                       'context': {'default_employee_id': self.employee_id.id}})
        return action
