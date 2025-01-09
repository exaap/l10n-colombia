# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from odoo import fields, models, api


class HrContractDeduction(models.Model):
    _name = 'hr.contract.deduction'
    _description = 'Periodic deductions or payments'

    input_id = fields.Many2one(
        comodel_name='hr.rule.input',
        string='Salary rule',
        required=True,
        help="Parameter associated with the salary rule")

    type = fields.Selection(string='Deduction Type',
                            selection=[('P', 'Company Loan'), ('A', 'Saving'),
                                       ('S', 'Sure'), ('L', 'Lien'),
                                       ('E', 'Embargo'), ('R', 'Retention'),
                                       ('O', 'Other')],
                            default='O',
                            required=True)

    period = fields.Selection(selection=[('limited', 'Limitado'),
                                         ('indefinite', 'Indefinido')],
                              default='indefinite',
                              string='Period',
                              required=True)
    amount = fields.Float(
        string='Amount',
        help=
        "Value of the quota or percentage according to the formula of the salary rule",
        default=0,
        required=True)

    total_deduction = fields.Float(string='Total Deduction',
                                   default=0,
                                   help="Total to Discount")
    total_accumulated = fields.Float(
        string='Previous accumulated',
        default=0,
        help="Total paid or accumulated of the concept")

    total_acumulados = fields.Float(string='Accumulated Odoo',
                                    compute='_compute_saldo',
                                    default=0.0,
                                    readonly=True)
    current_balance = fields.Float(string='Saldo actual',
                                   compute='_compute_saldo',
                                   default=0.0,
                                   readonly=True)
    date = fields.Date(string='Start date',
                       sindex=True,
                       help="Date of loan or obligation")
    date_end = fields.Date(string='Date End',
                           index=True,
                           help="Date End or obligation")

    appears_on_payslip = fields.Boolean(string='Appears on Payslip')

    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string='Contract',
                                  required=True,
                                  ondelete='cascade',
                                  index=True)

    @api.multi
    @api.depends('amount', 'period', 'total_deduction', 'total_accumulated')
    def _compute_saldo(self):
        for line in self:
            result = 0.0
            if line.period == 'limited' and line.date and line.date_end:
                #             self.env.cr.execute("""select  sum(l.total) as total
                #                      from hr_payslip_line l
                #                      inner join hr_payslip p on (p.id = l.slip_id)
                #                      inner join hr_payslip_input i on (i.payslip_id = p.id and i.salary_rule_id = l.salary_rule_id)
                #                      where i.deduction_id = %s""" %  (line.id,))

                # Basado solo en entradas
                self.env.cr.execute(
                    """select  coalesce(sum(i.amount),0.0) as total 
                      from hr_payslip_input i
                      inner join hr_payslip p on (p.id = i.payslip_id)
                      where i.deduction_id = %(prestamo_id)s
                      and p.date_from between %(fecha_desde)s::date and %(fecha_hasta)s::date
                      """, {
                        'prestamo_id': line.id or 0.0,
                        'fecha_desde': line.date,
                        'fecha_hasta': line.date_end,
                    })

                res = self.env.cr.fetchone() or False
                if res:
                    result = res[0] or 0.0
                    result = result

            line.total_acumulados = result
            line.current_balance = line.total_deduction - line.total_acumulados
