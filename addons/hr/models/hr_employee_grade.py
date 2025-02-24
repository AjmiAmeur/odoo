from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrEmployeeGrade(models.Model):
    _name = 'hr.employee.grade'
    _description = "Grades de la fonction publique "
    _order = "type,corps_id,categorie_administrative_id,name"

    name = fields.Char(string='Nom du grade', required=True,translate=True)
    type = fields.Selection([
        ('employee', 'Personnels IATOS'),
        ('enseignant', 'Enseignant'),
        ('visiteur', 'Visiteur'),
        ('vacataire', 'Vacataire'),
        ('student', 'Etudiant'),
        ('trainee', 'Stagiaire'),  
        ('other', 'Autre'),
        ], string="Types d'employé", default='employee', required=True, groups="hr.group_hr_user",
        help="Administratif/Enseignant/Visiteur/vacataire/Etudiant/Stagiaire/Autre")
    
    sous_type_id  = fields.Many2one('hr.sous.type', string="Sous-Type", required=True,domain="[('type', '=?', type)]",groups="hr.group_hr_user")

    corps_id  = fields.Many2one('hr.employee.corps', string="Corps", required=True,domain="[('sous_type_id', '=?', sous_type_id)]",groups="hr.group_hr_user")
    
    categorie_administrative_id  = fields.Many2one('hr.categorie.administrative', string="Catégorie administrative", groups="hr.group_hr_user",required=True)
    age_retraite = fields.Integer(string="Age de départ à la retraite", required=True, default=62)
    
    @api.constrains('age_retraite')
    def _check_age_retraite(self):
        for record in self:
            if record.age_retraite >= 100:
                raise ValidationError("L'âge de départ à la retraite doit être inférieur à 100.")

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Grade deja existe!"),
    ]
