# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _
from odoo.tools.sql import SQL
from collections import defaultdict


class DetachementHistory(models.Model):
    _name = 'hr.detachement.history'
    _description = 'Detachement history'
    _auto = False
    _order = 'is_under_detachement'

    # Even though it would have been obvious to use the reference detachement's id as the id of the
    # hr.detachement.history model, it turned out it was a bad idea as this id could change (for instance if a
    # new detachement is created with a later start date). The hr.detachement.history is instead closely linked
    # to the employee. That's why we will use this id (employee_id) as the id of the hr.detachement.history.
    detachement_id = fields.Many2one('hr.detachement', readonly=True)

    name = fields.Char('Detachement Name', readonly=True)
    date_hired = fields.Date('Hire Date', readonly=True)
    date_start = fields.Date('Start Date', readonly=True)
    date_end = fields.Date('End Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    active_employee = fields.Boolean('Active Employee', readonly=True)
    is_under_detachement = fields.Boolean('Is Currently Under Detachement', readonly=True)
    hr_responsible_id = fields.Many2one('res.users', string='HR Responsible', readonly=True)
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True)
    resource_calendar_id = fields.Many2one('resource.calendar', string="Working Schedule", readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_country_id = fields.Many2one('res.country', string="Company country", related='organisme_etranger_id.country_id', readonly=True)
    country_code = fields.Char(related='company_country_id.code', depends=['company_country_id'], readonly=True)
    detachement_ids = fields.One2many('hr.detachement', string='Detachements', compute='_compute_detachement_ids', readonly=True, compute_sudo=True)
    detachement_count = fields.Integer(compute='_compute_detachement_count', string="# Detachements")
    organisme_detachement_id = fields.Many2one(
        comodel_name='res.partner',
        string='Organisme de détachement en tunisie', ondelete='restrict',
        domain="['|', ('parent_id','=', False), ('is_company','=',True)]",
        help="Organisme de détachement en tunisie.")
    organisme_etranger_id = fields.Many2one(
        comodel_name='res.partner',
        string='Organisme de détachement à l’étranger', ondelete='restrict',
        domain="['|', ('parent_id','=', False), ('is_company','=',True)]",
        help="Organisme de détachement à l’étranger.")
    under_detachement_state = fields.Selection([
        ('done', 'Under Detachement'),
        ('blocked', 'Not Under Detachement')
    ], string='Detachementual Status', compute='_compute_under_detachement_state')
    activity_state = fields.Selection(related='detachement_id.activity_state')

    @api.depends('detachement_ids')
    def _compute_detachement_count(self):
        for history in self:
            history.detachement_count = len(history.detachement_ids)

    @api.depends('is_under_detachement')
    def _compute_under_detachement_state(self):
        for history in self:
            history.under_detachement_state = 'done' if history.is_under_detachement else 'blocked'

    @api.depends('employee_id.name')
    def _compute_display_name(self):
        for history in self:
            history.display_name = _("%s's Detachements History", history.employee_id.name)

    @api.model
    def _get_fields(self):
        return ','.join('detachement.%s' % name for name, field in self._fields.items()
                        if field.store 
                        and field.type not in ['many2many', 'one2many', 'related']
                        and field.name not in ['id', 'detachement_id', 'employee_id', 'date_hired', 'is_under_detachement', 'active_employee'])

    def _read_group_groupby(self, groupby_spec, query):
        if groupby_spec != 'activity_state':
            return super()._read_group_groupby(groupby_spec, query)

        Detachement = self.env['hr.detachement']
        # we use Detachement._table as the JOIN alias, because that's the one used
        # by the call to Detachement._read_group_groupby() below
        query.add_join('LEFT JOIN', Detachement._table, Detachement._table, SQL(
            "%s = %s",
            self._field_to_sql(self._table, 'detachement_id', query),
            SQL.identifier(Detachement._table, 'id'),
        ))
        activity_state_sql = Detachement._read_group_groupby(groupby_spec, query)
        # Change the kind of JOIN -> JOIN LEFT because
        # LEFT JOIN follow by JOIN doesn't have the same semantic
        __, table, condition = query._joins['hr_detachement__last_activity_state']
        query._joins['hr_detachement__last_activity_state'] = (SQL('LEFT JOIN'), table, condition)
        return activity_state_sql

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Reference detachement is the one with the latest start_date.
        self.env.cr.execute("""CREATE or REPLACE VIEW %s AS (
            WITH detachement_information AS (
                SELECT DISTINCT employee_id,
                                company_id,
                                FIRST_VALUE(id) OVER w_partition AS id,
                                MAX(CASE
                                    WHEN state='open' THEN 1
                                    WHEN state='draft' AND kanban_state='done' THEN 1
                                    ELSE 0 END) OVER w_partition AS is_under_detachement
                FROM   hr_detachement AS detachement
                WHERE  detachement.active = true
                WINDOW w_partition AS (
                    PARTITION BY detachement.employee_id, detachement.company_id
                    ORDER BY
                        CASE
                            WHEN detachement.state = 'open' THEN 0
                            WHEN detachement.state = 'draft' THEN 1
                            WHEN detachement.state = 'close' THEN 2
                            WHEN detachement.state = 'cancel' THEN 3
                            ELSE 4 END,
                        detachement.date_start DESC
                    RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                )
            )
            SELECT DISTINCT employee.id AS id,
                            employee.id AS employee_id,
                            employee.active AS active_employee,
                            detachement.id AS detachement_id,
                            detachement_information.is_under_detachement::bool AS is_under_detachement,
                            employee.first_detachement_date AS date_hired,
                            %s
            FROM       hr_detachement AS detachement
            INNER JOIN detachement_information ON detachement.id = detachement_information.id
            RIGHT JOIN hr_employee AS employee
                ON  detachement_information.employee_id = employee.id
                AND detachement.company_id = employee.company_id
            WHERE   employee.employee_type IN ('employee', 'student', 'trainee', 'enseignant')
        )""" % (self._table, self._get_fields()))

    @api.depends('employee_id.detachement_ids')
    def _compute_detachement_ids(self):
        sorted_detachements = self.mapped('employee_id.detachement_ids').sorted('date_start', reverse=True)

        mapped_employee_detachements = defaultdict(lambda: self.env['hr.detachement'])
        for detachement in sorted_detachements:
            mapped_employee_detachements[detachement.employee_id] |= detachement

        for history in self:
            history.detachement_ids = mapped_employee_detachements[history.employee_id]

    def hr_detachement_view_form_new_action(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hr_detachement.action_hr_detachement')
        action.update({
            'context': {'default_employee_id': self.employee_id.id},
            'view_mode': 'form',
            'view_id': self.env.ref('hr_detachement.hr_detachement_view_form').id,
            'views': [(self.env.ref('hr_detachement.hr_detachement_view_form').id, 'form')],
        })
        return action
