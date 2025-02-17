from odoo import models, fields

class HrEmployeeGrade(models.Model):
    _name = 'hr.employee.grade'
    _description = "Grades de la fonction publique "
    _order = "name"

    name = fields.Char(string='Grade Name', required=True,translate=True)
    description = fields.Text(string='Description')
    type = fields.Selection([
        ('employee', 'Administratif'),
        ('enseignant', 'Enseignant'),
        ('visiteur', 'Visiteur'),
        ('vacataire', 'Vacataire'),
        ('student', 'Etudiant'),
        ('trainee', 'Stagiaire'),  
        ('other', 'Autre'),
        ], string="Types d'employé", default='employee', required=True, groups="hr.group_hr_user",
        help="Administratif/Enseignant/Visiteur/vacataire/Etudiant/Stagiaire/Autre")
    corps_id  = fields.Many2one('hr.employee.corps', string="Corps", required=True,domain="[('type', '=?', type)]",groups="hr.group_hr_user")
    categorie_administrative_id  = fields.Many2one('hr.categorie.administrative', string="Catégorie administrative", groups="hr.group_hr_user",required=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Grade deja existe!"),
    ]
