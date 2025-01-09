# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrContractAnalytic(models.Model):
    _name = 'hr.contract.analytic'
    _description = 'Distribution by analytical account'

    percent = fields.Float(string='Percent', required=True, default=0)
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        required=True)
    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string='Analytic Account',
                                  required=True,
                                  ondelete='cascade',
                                  index=True)
