# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrContractSetting(models.Model):
    _name = 'hr.contract.setting'
    _description = 'Payroll configuration'

    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string='Contract',
                                  required=True,
                                  ondelete='cascade',
                                  index=True)
    contrib_id = fields.Many2one(comodel_name='hr.contribution.register',
                                 string='Concept',
                                 help="Contribution concept")
    partner_id = fields.Many2one(comodel_name='res.partner',
                                 string='Entity',
                                 help="Related entity")
    account_debit_id = fields.Many2one(comodel_name='account.account',
                                       string='Debit Account')
    account_credit_id = fields.Many2one(comodel_name='account.account',
                                        string='Credit Account')
