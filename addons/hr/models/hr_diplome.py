from odoo import models, fields

class HrDiplome(models.Model):
    _name = 'hr.diplome'
    _description = 'niveau de diplôme'
    _order = "name asc"
    

    name = fields.Char(string='Titre du diplôme	', help="Nomenclature relative au niveau de diplôme.", required=True, translate=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "diplôme deja existe!"),
    ]
