# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrContractChangeWage(models.Model):
    _name = 'hr.contract.change.wage'
    _description = 'Basic salary changes'
    _order = 'date_start desc'

    date_start = fields.Date(string='Start date', required=True)
    wage = fields.Float(string='Basic salary',
                        help="Tracking changes in basic salary",
                        required=True)
    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string='risks',
                                  required=True,
                                  ondelete='cascade',
                                  index=True)

    _sql_constraints = [
        ('change_wage_uniq', 'unique(contract_id, date_start)',
         'The date entered already exists'),
    ]
