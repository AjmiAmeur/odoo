# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.tools.sql import SQL
from collections import defaultdict


class DisponibiliteHistory(models.Model):
    _name = 'hr.disponibilite.history'
    _description = 'Historique des mises en disponibilité des employés'
    _auto = False
    _order = 'is_under_disponibilite'

    # Even though it would have been obvious to use the reference disponibilite's id as the id of the
    # hr.disponibilite.history model, it turned out it was a bad idea as this id could change (for instance if a
    # new disponibilite is created with a later start date). The hr.disponibilite.history is instead closely linked
    # to the employee. That's why we will use this id (employee_id) as the id of the hr.disponibilite.history.
    disponibilite_id = fields.Many2one('hr.disponibilite', readonly=True)

    name = fields.Char('Référence de la Mise en disponibilité', readonly=True)
    date_hired = fields.Date('Hire Date', readonly=True)
    date_start = fields.Date('Start Date', readonly=True)
    date_end = fields.Date('End Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    active_employee = fields.Boolean('Active Employee', readonly=True)
    is_under_disponibilite = fields.Boolean('Est actuellement en mise en disponibilité', readonly=True)
    hr_responsible_id = fields.Many2one('res.users', string='HR Responsible', readonly=True)
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_country_id = fields.Many2one('res.country', string="Company country", related='company_id.country_id', readonly=True)
    country_code = fields.Char(related='company_country_id.code', depends=['company_country_id'], readonly=True)
    disponibilite_ids = fields.One2many('hr.disponibilite', string='Mises en disponibilité', compute='_compute_disponibilite_ids', readonly=True, compute_sudo=True)
    disponibilite_count = fields.Integer(compute='_compute_disponibilite_count', string="# Mises en disponibilité")
    
    under_disponibilite_state = fields.Selection([
        ('done', 'En mise en disponibilité'),
        ('blocked', 'Pas en mise en disponibilité')
    ], string='Statut de la mise en disponibilité', compute='_compute_under_disponibilite_state')
    activity_state = fields.Selection(related='disponibilite_id.activity_state')

    @api.depends('disponibilite_ids')
    def _compute_disponibilite_count(self):
        for history in self:
            history.disponibilite_count = len(history.disponibilite_ids)

    @api.depends('is_under_disponibilite')
    def _compute_under_disponibilite_state(self):
        for history in self:
            history.under_disponibilite_state = 'done' if history.is_under_disponibilite else 'blocked'

    @api.depends('employee_id.name')
    def _compute_display_name(self):
        for history in self:
            history.display_name = _("%s's Disponibilites History", history.employee_id.name)

    @api.model
    def _get_fields(self):
        return ','.join('disponibilite.%s' % name for name, field in self._fields.items()
                        if field.store 
                        and field.type not in ['many2many', 'one2many', 'related']
                        and field.name not in ['id', 'disponibilite_id', 'employee_id', 'date_hired', 'is_under_disponibilite', 'active_employee'])

    def _read_group_groupby(self, groupby_spec, query):
        if groupby_spec != 'activity_state':
            return super()._read_group_groupby(groupby_spec, query)

        Disponibilite = self.env['hr.disponibilite']
        # we use Disponibilite._table as the JOIN alias, because that's the one used
        # by the call to Disponibilite._read_group_groupby() below
        query.add_join('LEFT JOIN', Disponibilite._table, Disponibilite._table, SQL(
            "%s = %s",
            self._field_to_sql(self._table, 'disponibilite_id', query),
            SQL.identifier(Disponibilite._table, 'id'),
        ))
        activity_state_sql = Disponibilite._read_group_groupby(groupby_spec, query)
        # Change the kind of JOIN -> JOIN LEFT because
        # LEFT JOIN follow by JOIN doesn't have the same semantic
        __, table, condition = query._joins['hr_disponibilite__last_activity_state']
        query._joins['hr_disponibilite__last_activity_state'] = (SQL('LEFT JOIN'), table, condition)
        return activity_state_sql

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Reference disponibilite is the one with the latest start_date.
        self.env.cr.execute("""CREATE or REPLACE VIEW %s AS (
            WITH disponibilite_information AS (
                SELECT DISTINCT employee_id,
                                company_id,
                                FIRST_VALUE(id) OVER w_partition AS id,
                                MAX(CASE
                                    WHEN state='open' THEN 1
                                    WHEN state='draft' AND kanban_state='done' THEN 1
                                    ELSE 0 END) OVER w_partition AS is_under_disponibilite
                FROM   hr_disponibilite AS disponibilite
                WHERE  disponibilite.active = true
                WINDOW w_partition AS (
                    PARTITION BY disponibilite.employee_id, disponibilite.company_id
                    ORDER BY
                        CASE
                            WHEN disponibilite.state = 'open' THEN 0
                            WHEN disponibilite.state = 'draft' THEN 1
                            WHEN disponibilite.state = 'close' THEN 2
                            WHEN disponibilite.state = 'cancel' THEN 3
                            ELSE 4 END,
                        disponibilite.date_start DESC
                    RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                )
            )
            SELECT DISTINCT employee.id AS id,
                            employee.id AS employee_id,
                            employee.active AS active_employee,
                            disponibilite.id AS disponibilite_id,
                            disponibilite_information.is_under_disponibilite::bool AS is_under_disponibilite,
                            employee.first_disponibilite_date AS date_hired,
                            %s
            FROM       hr_disponibilite AS disponibilite
            INNER JOIN disponibilite_information ON disponibilite.id = disponibilite_information.id
            RIGHT JOIN hr_employee AS employee
                ON  disponibilite_information.employee_id = employee.id
                AND disponibilite.company_id = employee.company_id
            WHERE   employee.employee_type IN ('employee', 'student', 'trainee', 'enseignant')
        )""" % (self._table, self._get_fields()))

    @api.depends('employee_id.disponibilite_ids')
    def _compute_disponibilite_ids(self):
        sorted_disponibilites = self.mapped('employee_id.disponibilite_ids').sorted('date_start', reverse=True)

        mapped_employee_disponibilites = defaultdict(lambda: self.env['hr.disponibilite'])
        for disponibilite in sorted_disponibilites:
            mapped_employee_disponibilites[disponibilite.employee_id] |= disponibilite

        for history in self:
            history.disponibilite_ids = mapped_employee_disponibilites[history.employee_id]

    def hr_disponibilite_view_form_new_action(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hr_disponibilite.action_hr_disponibilite')
        action.update({
            'context': {'default_employee_id': self.employee_id.id},
            'view_mode': 'form',
            'view_id': self.env.ref('hr_disponibilite.hr_disponibilite_view_form').id,
            'views': [(self.env.ref('hr_disponibilite.hr_disponibilite_view_form').id, 'form')],
        })
        return action
