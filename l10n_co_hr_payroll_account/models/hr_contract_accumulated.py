# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models


class HrContractAccumulated(models.Model):

    _name = 'hr.contract.accumulated'
    _description = 'Accumulated contract'
    _order = 'date, contract_id, salary_rule_id'

    date = fields.Date(string='Date')
    salary_rule_id = fields.Many2one(comodel_name='hr.salary.rule',
                                     required=True,
                                     string='Salary rule')
    amount = fields.Float(string='Value', required=True, default=0)
    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string='Contract',
                                  required=True,
                                  ondelete='cascade',
                                  index=True)
