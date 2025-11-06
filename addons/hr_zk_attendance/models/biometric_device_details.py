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
import datetime
import logging
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date


_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Please install the library: pip3 install zk.")


class BiometricDeviceDetails(models.Model):
    """Model for configuring and connect the biometric device with odoo"""
    _name = 'biometric.device.details'
    _description = 'Biometric Device Details'

    name = fields.Char(string='Name', required=True, help='Record Name')
    device_ip = fields.Char(string='Device IP', required=True,
                            help='The IP address of the Device')
    port_number = fields.Integer(string='Port Number', required=True,
                                 help="The Port Number of the Device")
    address_id = fields.Many2one('res.partner', string='Working Address',
                                 help='Working address of the partner')
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda
                                     self: self.env.user.company_id.id,
                                 help='Current Company')

    def device_connect(self, zk):
        """Function for connecting the device with Odoo"""
        try:
            conn = zk.connect()
            return conn
        except Exception:
            return False

    def action_test_connection(self):
        """Checking the connection status"""
        zk = ZK(self.device_ip, port=self.port_number, timeout=30,
                password=False, ommit_ping=False)
        try:
            if zk.connect():
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Successfully Connected',
                        'type': 'success',
                        'sticky': False
                    }
                }
        except Exception as error:
            raise ValidationError(f'{error}')

    def action_set_timezone(self):
        """Function to set user's timezone to device"""
        for info in self:
            machine_ip = info.device_ip
            zk_port = info.port_number
            try:
                # Connecting with the device with the ip and port provided
                zk = ZK(machine_ip, port=zk_port, timeout=15,
                        password=0,
                        force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(
                    _("Pyzk module not Found. Please install it"
                      "with 'pip3 install pyzk'."))
            conn = self.device_connect(zk)
            if conn:
                user_tz = self.env.context.get(
                    'tz') or self.env.user.tz or 'UTC'
                user_timezone_time = pytz.utc.localize(fields.Datetime.now())
                user_timezone_time = user_timezone_time.astimezone(
                    pytz.timezone(user_tz))
                conn.set_time(user_timezone_time)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Successfully Set the Time',
                        'type': 'success',
                        'sticky': False
                    }
                }
            else:
                raise UserError(_(
                    "Please Check the Connection"))

    def action_clear_attendance(self):
        """Methode to clear record from the zk.machine.attendance model and
        from the device"""
        for info in self:
            try:
                machine_ip = info.device_ip
                zk_port = info.port_number
                try:
                    # Connecting with the device
                    zk = ZK(machine_ip, port=zk_port, timeout=30,
                            password=0, force_udp=False, ommit_ping=True)
                except NameError:
                    raise UserError(_(
                        "Please install it with 'pip3 install pyzk'."))
                conn = self.device_connect(zk)
                if conn:
                    conn.enable_device()
                    clear_data = zk.get_attendance()
                    if clear_data:
                        # Clearing data in the device
                        conn.clear_attendance()
                        # Clearing data from attendance log
                        self._cr.execute(
                            """delete from zk_machine_attendance""")
                        conn.disconnect()
                    else:
                        raise UserError(
                            _('Unable to clear Attendance log.Are you sure '
                              'attendance log is not empty.'))
                else:
                    raise UserError(
                        _('Unable to connect to Attendance Device. Please use '
                          'Test Connection button to verify.'))
            except Exception as error:
                raise ValidationError(f'{error}')

    @api.model
    def cron_download(self):
        machines = self.env['biometric.device.details'].search([])
        for machine in machines:
            machine.action_download_attendance()


    def action_download_attendance(self):
        """Import only today's attendance logs using employee PIN."""
        _logger.info(">>> Biometric sync START (today only, map by PIN)")

        zk_attendance = self.env['zk.machine.attendance']

        today_min = fields.Datetime.to_string(datetime.combine(date.today(), datetime.min.time()))
        today_max = fields.Datetime.to_string(datetime.combine(date.today(), datetime.max.time()))

        for device in self:
            zk = ZK(device.device_ip, port=device.port_number, timeout=15, password=0,
                    force_udp=False, ommit_ping=True)

            conn = self.device_connect(zk)
            if not conn:
                raise UserError(_("Unable to connect to the device. Check IP/Port."))

            conn.disable_device()
            logs = conn.get_attendance()

            if not logs:
                conn.enable_device()
                conn.disconnect()
                raise UserError(_("No attendance logs found on device."))

            new_logs = []
            for log in logs:
                punch_dt = fields.Datetime.to_string(log.timestamp)
                if today_min <= punch_dt <= today_max:
                    new_logs.append(log)

            if not new_logs:
                conn.enable_device()
                conn.disconnect()
                _logger.info(">>> No logs for today")
                return True

            _logger.info(f">>> Logs to import today: {len(new_logs)}")

            batch = []
            BATCH_SIZE = 500

            for entry in new_logs:
                _logger.info(f"USER_ID depuis pointeuse = {entry.user_id}, Punch = {entry.punch}, Time = {entry.timestamp}")

                employee = self.env['hr.employee'].search([
                    '|', ('pin', '=', str(entry.user_id)), ('pin', '=', entry.user_id),
                ], limit=1)
                if not employee:
                    _logger.warning(f"⚠️ Aucun employé trouvé avec PIN = {entry.user_id}")
                    continue
                punching_time = fields.Datetime.to_string(entry.timestamp)

                # ✅ Empêcher doublons (sans filtrer par address_id)
                exists = zk_attendance.search([
                    ('employee_id', '=', employee.id),
                    ('punching_time', '=', punching_time),
                    ('punch_type', '=', str(entry.punch)),
                ], limit=1)

                if exists:
                    _logger.info(f"⏩ Pointage déjà existant - Ignoré ({employee.name} - {punching_time})")
                    continue

                data = {
                    'employee_id': employee.id,
                    'device_id_num': entry.user_id,
                    'attendance_type': str(entry.status),
                    'punch_type': str(entry.punch),
                    'punching_time': punching_time,
                    'check_in': punching_time,
                    'address_id': device.address_id.id,   # On garde la valeur, mais pas dans la recherche
                }
                batch.append(data)

                if len(batch) >= BATCH_SIZE:
                    zk_attendance.create(batch)
                    batch = []

            if batch:
                zk_attendance.create(batch)

            conn.enable_device()
            conn.disconnect()

            _logger.info(">>> Biometric sync COMPLETED (today only)")
            return True
    def action_restart_device(self):
        """For restarting the device"""
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=0,
                force_udp=False, ommit_ping=True)
        self.device_connect(zk).restart()
    #*************
    def action_sync_to_hr_attendance(self):
        Attendance = self.env['hr.attendance']
        MachineLogs = self.env['zk.machine.attendance']

        # Récupération des logs triés
        logs = MachineLogs.search([], order="employee_id, punching_time")

        if not logs:
            raise UserError(_("Aucun pointage trouvé à convertir."))

        for log in logs:
            employee = log.employee_id
            if not employee:
                continue

            # Check-In (Entrée)
            if log.punch_type == '0':  
                # vérifier s'il existe une présence ouverte
                open_attendance = Attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False)
                ], limit=1)

                if not open_attendance:
                    Attendance.create({
                        'employee_id': employee.id,
                        'check_in': log.punching_time,
                    })
                else:
                    # Déjà entré → on ignore
                    continue

            # Check-Out (Sortie)
            elif log.punch_type == '1':
                open_attendance = Attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False)
                ], limit=1)

                if open_attendance:
                    open_attendance.write({
                        'check_out': log.punching_time
                    })
                else:
                    # Sortie sans entrée → on crée entrée automatique
                    Attendance.create({
                        'employee_id': employee.id,
                        'check_in': log.punching_time,
                        'check_out': log.punching_time,
                    })

        return True