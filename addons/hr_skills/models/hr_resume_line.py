# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from dateutil.relativedelta import relativedelta
from datetime import date



class ResumeLine(models.Model):
    _name = 'hr.resume.line'
    _description = "Resume line of an employee"
    _order = "line_type_id, date_end desc, date_start desc"

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True, translate=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date()
    description = fields.Html(string="Description", translate=True)
    interruption_reason = fields.Text(string="Motif de l'interruption", help="Explain why the activity was interrupted.", translate=True)
    observation = fields.Text(string="observation", help="observation.", translate=True)

    line_type_id = fields.Many2one('hr.resume.line.type', string="Type")

    # Used to apply specific template on a line
    display_type = fields.Selection([('classic', 'Classic')], string="Display Type", default='classic')

    duration_days = fields.Integer(string="Duration (Days)", compute="_compute_duration", store=False)
    duration_months = fields.Integer(string="Duration (Months)", compute="_compute_duration", store=False)
    duration_years = fields.Integer(string="Duration (Years)", compute="_compute_duration", store=False)
    duration_display = fields.Char(string="Durée", compute="_compute_duration", store=False)


    _sql_constraints = [
        ('date_check', "CHECK ((date_start <= date_end OR date_end IS NULL))", "The start date must be anterior to the end date."),
    ]
    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            start = rec.date_start
            end = rec.date_end or date.today()

            if not start or end < start:
                rec.duration_years = 0
                rec.duration_months = 0
                rec.duration_days = 0
                rec.duration_display = "0 jour"
                continue

            delta = relativedelta(end, start)

            rec.duration_years = delta.years
            rec.duration_months = delta.months
            rec.duration_days = delta.days

            parts = []
            if delta.years:
                parts.append(f"{delta.years} an{'s' if delta.years > 1 else ''}")
            if delta.months:
                parts.append(f"{delta.months} mois")
            if delta.days:
                parts.append(f"{delta.days} jour{'s' if delta.days > 1 else ''}")

            rec.duration_display = ", ".join(parts) if parts else "0 jour"
