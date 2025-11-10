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
import socket


_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Please install the library: pip3 install zk.")


class BiometricDeviceDetails(models.Model):
    """Model for configuring and connect the biometric device with odoo"""
    _name = 'hr.zk.biometric.device.details'
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
    # ⬇️ Ajout du champ statut
    device_status = fields.Selection(
        [('online', 'Online'), ('offline', 'Offline')],
        string="Statut",
        compute="_compute_device_status",
        store=False
    )
    device_status_display = fields.Char(string="Statut", compute="_compute_device_status")

    @api.depends('device_ip', 'port_number')
    def _compute_device_status(self):
        for rec in self:
            rec.device_status = 'offline'
            rec.device_status_display = "🔴 Offline"
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.5)   # Timeout court
                result = sock.connect_ex((rec.device_ip, rec.port_number))
                sock.close()
                if result == 0:
                    rec.device_status = 'online'
                    rec.device_status_display = "🟢 Online"
            except:
                rec.device_status = 'offline'
                rec.device_status_display = "🔴 Offline"


    def device_connect(self, zk):
        """Function for connecting the device with Odoo"""
        try:
            conn = zk.connect()
            return conn
        except Exception:
            return False

    def action_test_connection(self):
        self.ensure_one()

        ip = self.device_ip
        port = self.port_number

        # ----- Test réseau rapide (pas de blocage) -----
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)  # ⏱ Timeout 3 secondes maximum

        try:
            result = sock.connect_ex((ip, port))
            sock.close()

            if result != 0:
                # Port fermé → on stoppe ici → pas de hang
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f"❌ Impossible de se connecter à {ip}:{port}. (Port fermé ou machine hors ligne)",
                        'type': 'danger',
                        'sticky': False,
                    }
                }

        except Exception:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f"❌ Test réseau échoué vers {ip}.",
                    'type': 'danger',
                    'sticky': False,
                }
            }

        # ----- Si le port répond → on tente la connexion ZK -----
        try:
            zk = ZK(ip, port=port, timeout=5, password=0, ommit_ping=True)
            conn = zk.connect()
            conn.disconnect()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': "✅ Connexion réussie",
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f"❌ Pointeuse détectée mais non accessible : {e}",
                    'type': 'danger',
                    'sticky': False,
                }
            }

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

    def action_clear_device_logs(self):
        """Effacer le journal de présence dans la pointeuse uniquement"""
        for device in self:
            try:
                zk = ZK(device.device_ip, port=device.port_number, timeout=30,
                        password=0, force_udp=False, ommit_ping=True)

                conn = device.device_connect(zk)
                if not conn:
                    raise UserError(_("Impossible de se connecter à la pointeuse."))

                conn.enable_device()
                clear_data = zk.get_attendance()

                if clear_data:
                    conn.clear_attendance()
                    conn.disconnect()
                else:
                    raise UserError(_("Aucun pointage trouvé dans la pointeuse."))

            except Exception as error:
                raise ValidationError(f"{error}")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": _("Données effacées de la pointeuse ✅"), "type": "success"}
        }

    def action_clear_odoo_logs(self):
        """Effacer les logs uniquement dans le modèle Odoo"""
        self.env.cr.execute("""DELETE FROM hr_zk_machine_attendance""")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": _("Données effacées dans Odoo ✅"), "type": "success"}
        }

    def action_clear_attendance(self):
        """Effacer les données dans la pointeuse + Odoo (méthode complète)"""
        self.action_clear_device_logs()
        self.action_clear_odoo_logs()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": _("Nettoyage complet effectué ✅"), "type": "success"}
        }


    @api.model
    def cron_download(self):
        machines = self.env['hr.zk.biometric.device.details'].search([])
        for machine in machines:
            machine.action_download_attendance()


    def action_download_attendance(self):
        """Import ALL attendance logs using employee PIN (correct UTC conversion)."""
        _logger.info(">>> Biometric sync START (ALL logs, map by PIN)")

        zk_attendance = self.env['hr.zk.machine.attendance']
        tz = pytz.timezone('Africa/Tunis')

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

            _logger.info(f">>> Total logs to import: {len(logs)}")

            batch = []
            BATCH_SIZE = 500

            for entry in logs:
                employee = self.env['hr.employee'].search([
                    '|', ('pin', '=', str(entry.user_id)), ('pin', '=', entry.user_id),
                ], limit=1)

                if not employee:
                    _logger.warning(f"⚠️ Aucun employé trouvé avec PIN = {entry.user_id}")
                    continue

                # Conversion locale → UTC → datetime naïf (Odoo exige naive datetime)
                local_ts = tz.localize(entry.timestamp)
                utc_ts = local_ts.astimezone(pytz.utc)
                punching_time = utc_ts.replace(tzinfo=None)

                # Vérifier si le pointage existe déjà
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
                    'device_id': device.id,
                    'attendance_type': str(entry.status),
                    'punch_type': str(entry.punch),
                    'punching_time': punching_time,  # UTC naive
                    'check_in': punching_time,       # affiché selon TZ utilisateur
                    'address_id': device.address_id.id,
                }
                batch.append(data)

                if len(batch) >= BATCH_SIZE:
                    zk_attendance.create(batch)
                    batch = []

            # Créer le reste du batch
            if batch:
                zk_attendance.create(batch)

            conn.enable_device()
            conn.disconnect()

        _logger.info(">>> Biometric sync COMPLETED (ALL logs)")
        return True


    def action_download_attendance_range(self, date_start, date_end):
        _logger.info(f">>> Biometric sync START (range {date_start} → {date_end})")

        zk_attendance = self.env['hr.zk.machine.attendance']
        tz = pytz.timezone('Africa/Tunis')

        # ✅ Convertir les dates en datetimes (début & fin journée)
        date_start_dt = datetime.combine(date_start, datetime.min.time())
        date_end_dt = datetime.combine(date_end, datetime.max.time())

        start_local = tz.localize(date_start_dt)
        end_local = tz.localize(date_end_dt)

        for device in self:
            zk = ZK(device.device_ip, port=device.port_number, timeout=15, password=0,
                    force_udp=False, ommit_ping=True)

            conn = self.device_connect(zk)
            if not conn:
                raise UserError(_("Unable to connect to the device. Check IP/Port."))

            conn.disable_device()
            logs = conn.get_attendance()   # ✅ Pas d'argument start/end

            if not logs:
                conn.enable_device()
                conn.disconnect()
                raise UserError(_("No attendance logs found on device."))

            _logger.info(f">>> Total logs retrieved: {len(logs)}")

            # ✅ Filtrer les logs du range
            logs = [l for l in logs if start_local <= tz.localize(l.timestamp) <= end_local]
            _logger.info(f">>> Logs kept within range: {len(logs)}")

            batch = []
            BATCH_SIZE = 500

            for entry in logs:
                employee = self.env['hr.employee'].search([
                    '|', ('pin', '=', str(entry.user_id)), ('pin', '=', entry.user_id),
                ], limit=1)

                if not employee:
                    continue

                # ✅ Conversion locale → UTC → naïf
                local_ts = tz.localize(entry.timestamp)
                utc_ts = local_ts.astimezone(pytz.utc)
                punching_time = utc_ts.replace(tzinfo=None)

                exists = zk_attendance.search([
                    ('employee_id', '=', employee.id),
                    ('punching_time', '=', punching_time),
                    ('punch_type', '=', str(entry.punch)),
                ], limit=1)

                if exists:
                    continue

                batch.append({
                    'employee_id': employee.id,
                    'device_id_num': entry.user_id,
                    'device_id': device.id,
                    'attendance_type': str(entry.status),
                    'punch_type': str(entry.punch),
                    'punching_time': punching_time,
                    'check_in': punching_time,
                    'address_id': device.address_id.id,
                })

                if len(batch) >= BATCH_SIZE:
                    zk_attendance.create(batch)
                    batch = []

            if batch:
                zk_attendance.create(batch)

            conn.enable_device()
            conn.disconnect()

        _logger.info(">>> Biometric sync COMPLETED (range)")
        return True

    def _convert_logs_to_hr(self, logs):
        hr_attendance = self.env['hr.attendance']

        for log in logs:
            employee = log.employee_id
            if not employee:
                continue

            punch_time = log.punching_time

            # check-in
            if log.punch_type == '0':
                last_attendance = hr_attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                ], limit=1)
                if not last_attendance:
                    hr_attendance.create({
                        'employee_id': employee.id,
                        'check_in': punch_time,
                    })

            # check-out
            else:
                last_attendance = hr_attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                ], limit=1)
                if last_attendance:
                    last_attendance.write({'check_out': punch_time})
       
    
    def action_restart_device(self):
        """For restarting the device"""
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=0,
                force_udp=False, ommit_ping=True)
        self.device_connect(zk).restart()
    #*************
    def action_sync_to_hr_attendance(self):
        Attendance = self.env['hr.attendance']
        MachineLogs = self.env['hr.zk.machine.attendance']

        # Récupération des logs triés
        logs = MachineLogs.search([], order="employee_id, punching_time asc")


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
    def open_import_wizard(self):
        return {
            'name': _("Importer pointages"),
            'type': 'ir.actions.act_window',
            'res_model': 'zk.attendance.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_ids': self.ids},
        }