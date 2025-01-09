# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrPayslipAnalytic(models.Model):
    _name = 'hr.payslip.analytic'
    _description = 'Rule distribution by analytical account'
    _order = 'salary_rule_id'

    salary_rule_id = fields.Many2one(comodel_name='hr.salary.rule',
                                     string='Salary Rule',
                                     required=True)
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analityc Account',
        required=True)
    percent = fields.Float(string='Percent', required=True, default=0)
    slip_id = fields.Many2one(comodel_name='hr.payslip',
                              string='Payroll',
                              required=True,
                              ondelete='cascade',
                              index=True)

    _sql_constraints = [
        ('rule_analytic_uniq',
         'unique(slip_id, salary_rule_id, account_analytic_id)',
         'The distribution for the same rule and analytical account must be unique'
         ),
    ]
