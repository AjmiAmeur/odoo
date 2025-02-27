from odoo import models, fields

class HrDomaine(models.Model):
    _name = 'hr.domaine'
    _description = 'Domaines de spécialité'
    _order = "code asc"
    

    code = fields.Char(string='Code domaine', size=4, required=True)
    name = fields.Char(string='Nom de Domaine', help="Domaines de spécialité.", required=True, translate=True)

    _sql_constraints = [
        ('code_uniq', 'unique (code)', "code deja existe!"),
    ]
