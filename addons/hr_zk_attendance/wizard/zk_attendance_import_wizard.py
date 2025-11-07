from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, time


class ZKAttendanceImportWizard(models.TransientModel):
    _name = "zk.attendance.import.wizard"
    _description = "Wizard Import Attendance by Period"

    date_start = fields.Date(string="Date début", default=fields.Date.today)
    date_end = fields.Date(string="Date fin", default=fields.Date.today)
    progress = fields.Integer(string="Progression", default=0)

    def action_import(self):
        if self.date_end < self.date_start:
            raise UserError(_("La date de fin doit être supérieure à la date de début."))

        devices = self.env['hr.zk.biometric.device.details'].search([])
        if not devices:
            raise UserError(_("Aucun appareil biométrique configuré."))

        total_steps = len(devices) + 1  # +1 = phase conversion
        done = 0

        # ✅ Phase 1 : Import dans la période
        for device in devices:
            device.action_download_attendance_range(self.date_start, self.date_end)

            done += 1
            self.progress = int((done * 100) / total_steps)
            self.env.cr.commit()  # 🔥 Mise à jour directe dans la base

        # ✅ Phase 2 : Conversion des logs en hr.attendance
        self.env['hr.zk.biometric.device.details'].action_sync_to_hr_attendance()

        done += 1
        self.progress = int((done * 100) / total_steps)
        self.env.cr.commit()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _("Importation terminée avec succès ✅"),
                'type': 'success',
            }
        }
