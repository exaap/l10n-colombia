# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import models, fields


class HrPayslipDetails(models.Model):
    _name = 'hr.payslip.details'
    _description = 'Detail of the wage rules for social benefits'
    _order = 'salary_rule_id'

    slip_id = fields.Many2one(comodel_name='hr.payslip',
                              string='Payroll',
                              required=True,
                              ondelete='cascade',
                              index=True)
    salary_rule_id = fields.Many2one(comodel_name='hr.salary.rule',
                                     string='Salary Rule',
                                     required=True)
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To', required=True)
    days_total = fields.Integer(string='Total Days', required=True, default=0)
    days_leave = fields.Integer(string='Days Leave', required=True, default=0)
    days_neto = fields.Float(string='Days Net', required=True, default=0)
    wage_actual = fields.Float(string='Wage Actual', required=True, default=0)
    wage_total = fields.Float(string='Wage Total', required=True, default=0)
    wage_average = fields.Float(string='Wage Average',
                                required=True,
                                default=0)
    variable_total = fields.Float(string='Total variable',
                                  required=True,
                                  default=0)
    variable_average = fields.Float(string='Average variable',
                                    required=True,
                                    default=0)
    subsidization_transport = fields.Float(string='Subsidization transport',
                                           required=True,
                                           default=0)
    total_average = fields.Float(string='Base', required=True, default=0)
    amount = fields.Float(string='Net', required=True, default=0)
    detail_calc = fields.Text(string='Calculation detail')

    _sql_constraints = [
        ('_uniq', 'unique(slip_id, salary_rule_id)',
         'There is already a rule for the same payroll'),
    ]
