from odoo import models, fields

class HrCategorieAdministrative(models.Model):
    _name = 'hr.categorie.administrative'
    _description = 'Catégorie:Administration publique'
    _order = "name"

    name = fields.Char(string="Catégorie administrative", required=True, translate=True)
   
   
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Catégorie administrative deja existe!"),
    ]
