# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrDepartmentSalaryRule(models.Model):
    _name = 'hr.department.salary.rule'
    _description = 'Accounting accounts by department'

    department_id = fields.Many2one(comodel_name='hr.department',
                                    string='Departament',
                                    required=True,
                                    ondelete='cascade',
                                    index=True)
    salary_rule_id = fields.Many2one(comodel_name='hr.salary.rule',
                                     string='Salary rule',
                                     required=True)
    account_debit_id = fields.Many2one(comodel_name='account.account',
                                       string='Debit Account')
    account_credit_id = fields.Many2one('account.account',
                                        string='Credit Account')

    _sql_constraints = [
        ('department_rule_uniq', 'unique(department_id, salary_rule_id)',
         'The rule must be unique per department. The entered rule already exists'
         ),
    ]
