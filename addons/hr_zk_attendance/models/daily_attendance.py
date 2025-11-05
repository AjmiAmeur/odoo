# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Bhagyadev KP (odoo@cybrosys.com)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
from odoo import fields, models, tools


class DailyAttendance(models.Model):
    """Model to hold data from the biometric device"""
    _name = 'daily.attendance'
    _description = 'Daily Attendance Report'
    _auto = False
    _order = 'punching_day desc'

    employee_id = fields.Many2one('hr.employee', string='Employee',
                                  help='Employee Name')
    punching_day = fields.Datetime(string='Date', help='Date of punching')
    address_id = fields.Many2one('res.partner', string='Working Address',
                                 help='Working address of the employee')
    attendance_type = fields.Selection([('1', 'Finger'), ('15', 'Face'),
                                        ('2', 'Type_2'), ('3', 'Password'),
                                        ('4', 'Card')], string='Category',
                                       help='Attendance detecting methods')
    punch_type = fields.Selection([('0', 'Check In'), ('1', 'Check Out'),
                                   ('2', 'Break Out'), ('3', 'Break In'),
                                   ('4', 'Overtime In'), ('5', 'Overtime Out')],
                                  string='Punching Type',
                                  help='The Punching Type of attendance')
    punching_time = fields.Datetime(string='Punching Time',
                                    help='Punching time in the device')

    def init(self):
        """Retrieve the data for attendance report"""
        tools.drop_view_if_exists(self._cr, 'daily_attendance')
        query = """
            CREATE OR REPLACE VIEW daily_attendance AS (
                SELECT
                    z.id AS id,
                    z.employee_id AS employee_id,
                    date(z.punching_time) AS punching_day,
                    z.address_id AS address_id,
                    z.attendance_type AS attendance_type,
                    z.punching_time AS punching_time,
                    z.punch_type AS punch_type
                FROM zk_machine_attendance z
                JOIN hr_employee e ON z.employee_id = e.id
                ORDER BY z.punching_time
            );
        """
        self._cr.execute(query)

