# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import time
from datetime import datetime, timedelta, time
from dateutil import relativedelta
import babel
from pytz import timezone
from odoo import api, fields, models, tools, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, ValidationError

columnas = ['Fecha', 'Nómina No.', 'Regla salarial', 'Valor']
col_fecha = []
col_nomina = []
col_regla = []
col_valor = []


def limpiar_lineas():
    col_fecha = []
    col_nomina = []
    col_regla = []
    col_valor = []


def grabar_linea(fecha, nomina, regla, valor):
    col_fecha.append(fecha)
    col_nomina.append(nomina)
    col_regla.append(regla)
    col_valor.append(valor)


def grabar_linea2(concepto, valor):
    col_fecha.append('')
    col_nomina.append('')
    col_regla.append(concepto)
    col_valor.append(valor)


def linea_blanco():
    col_fecha.append('')
    col_nomina.append('')
    col_regla.append('')
    col_valor.append('')


def grabar_datos(result):
    total = 0
    for dato in result:
        grabar_linea(dato[0], dato[1], dato[2], dato[3])
        total += dato[3]

    grabar_linea('', '', 'Total', total)
    linea_blanco()


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'
    _description = 'Pay Slip'

    liquid = fields.Boolean(
        'Liquidación',
        default=False,
        help=
        "Indica si se ejecuta una estructura para liquidacion de contratos y vacaciones"
    )
    deduction_line_ids = fields.One2many(
        string='Detail of Deductions',
        comodel_name='hr.payslip.deduction.line',
        inverse_name='slip_id',
        readonly=True)
    analytic_ids = fields.One2many(comodel_name='hr.payslip.analytic',
                                   inverse_name='slip_id',
                                   string='Analytical accounts distribution')
    details_ids = fields.One2many(comodel_name='hr.payslip.details',
                                  inverse_name='slip_id',
                                  string='Detail calculations')
    date_bunus = fields.Date(string='Bunus liquidation date')
    date_layoff_fund = fields.Date(string='Date Layoff Fund')
    date_holidays = fields.Date(string='Holiday liquidation date')
    date_liquidation = fields.Date(string="Contract liquidation date")
    date_payment = fields.Date(string='Date Payment')
    payment_id = fields.Many2one(comodel_name='account.payment',
                                 string='Egress No.')
    move_bank_id = fields.Many2one(comodel_name='account.move',
                                   string='Payment accounting entry')
    move_bank_name = fields.Char(string='Payment number')
    struct_liquida_id = fields.Many2one(
        comodel_name='hr.payroll.structure',
        string='Salary structure',
        help=
        "Define the salary structure that will be used for the settlement of contracts and vacations"
    )
    type_liquid = fields.Selection(selection=[
        ('nomina', 'Solo nómina'),
        ('otro', 'Solo vacaciones / contratos / primas'),
        ('nomi_otro', 'Nómina y vacaciones / contratos / primas)')
    ],
                                   string='Type liquidation',
                                   required=True,
                                   default='nomina')
    motive_retirement = fields.Char(string='Motive Retirement', required=False)
    recover = fields.Boolean(
        string='Retrieve news',
        help=
        "Indicates if the news is loaded again before doing the calculations",
        default=True)
    identification_id = fields.Char(related="employee_id.identification_id",
                                    store=True,
                                    string='Identificación')
    journal_voucher_id = fields.Many2one(
        comodel_name='account.journal',
        string='Payment journal',
        help="Define the journal to make payments or proof of expenditure")
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('verify', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Rejected'),
            ('paid', 'Pagada'),
        ],
        string='Status',
        index=True,
        readonly=True,
        copy=False,
        default='draft',
        help="""* When the payslip is created the status is \'Draft\'
                \n* If the payslip is under verification, the status is \'Waiting\'.
                \n* If the payslip is confirmed then status is set to \'Done\'.
                \n* When user cancel payslip the status is \'Rejected\'.""")

    @api.multi
    def get_all_structures(self):
        """
        Adiciona funcion para encontrar las estructuras        
        """
        if not self.struct_liquida_id:
            return []

        return list(set(self.struct_liquida_id._get_parent_structure().ids))

    @api.multi
    def process_unlink_payment(self):
        # Elimina el comprobante de egreso
        for slip in self:
            #si esta asentado debe cancelarlo primero
            if slip.move_bank_id:
                for line in slip.move_bank_id.line_ids:
                    # refresh to make sure you don't unreconcile an already unreconciled entry
                    line.refresh()
                    if line.full_reconcile_id:
                        move_lines = [
                            move_line.id for move_line in
                            line.full_reconcile_id.reconciled_line_ids
                        ]
                        move_lines.remove(line.id)
                        line.remove_move_reconcile()

            if slip.payment_id and slip.payment_id.state == 'posted':
                slip.payment_id.cancel()

        return self.write({'move_bank_id': None, 'state': 'done'})

    @api.multi
    def process_unlink_voucher(self):
        # Elimina los asientos contables
        move_pool = self.env['account.move']
        for slip in self:
            #si esta asentado debe cancelarlo primero
            if slip.move_bank_id:
                for line in slip.move_bank_id.line_ids:
                    # refresh to make sure you don't unreconcile an already unreconciled entry
                    line.refresh()
                    if line.full_reconcile_id:
                        move_lines = [
                            move_line.id for move_line in
                            line.full_reconcile_id.reconciled_line_ids
                        ]
                        move_lines.remove(line.id)
                        line.remove_move_reconcile()

                    slip.move_bank_id.unlink()

        return self.write({'move_bank_id': None, 'state': 'done'})

    @api.multi
    def process_payment(self):
        # Este procedimiento crea el comprobante de egreso y luego lo contabiliza
        slip_line_obj = self.env['hr.payslip.line']
        move_obj = self.env['account.move.line']
        precision = self.env['decimal.precision'].precision_get('Payroll')

        for slip in self:
            print('* slip: ', slip.number)
            if not slip.journal_voucher_id:
                raise UserError(_('Debe primero ingresar el diario de pago'))

            if not slip.date_payment:
                raise UserError(
                    _('Debe primero ingresar la fecha de contabilización del pago'
                      ))

            #Busca el neto pagado
            slip_line_ids = slip_line_obj.search([('slip_id', '=', slip.id),
                                                  ('code', '=', 'NETO')])
            if not slip_line_ids:
                raise UserError(
                    _('La nómina "%s" no presenta neto a pagar. Recalcular y recontabilizar esta nómina o eliminarla'
                      ) % (slip.number))

            if slip_line_ids:
                currency = slip.company_id.currency_id or slip.journal_id.company_id.currency_id
                for line in slip_line_ids:

                    if line.total != 0.0:
                        line_ids = []

                        acc_id = slip.journal_voucher_id.default_credit_account_id.id
                        if not acc_id:
                            raise UserError(
                                _('El diario "%s" no tiene configurado la cuenta crédito!'
                                  ) % (slip.journal_voucher_id.name))

                        acc_id = slip.journal_id.default_debit_account_id.id
                        if not acc_id:
                            raise UserError(
                                _('El diario "%s" no tiene configurado la cuenta débito!'
                                  ) % (slip.journal_id.name))

                        #Busca la causación

                        lines = move_obj.search([
                            ('move_id', '=', slip.move_id.id),
                            ('account_id', '=',
                             slip.journal_id.default_credit_account_id.id),
                            ('credit', '=', currency.round(line.total))
                        ])
                        if not lines:
                            raise UserError(
                                _('La nómina "%s" no presenta una cuenta por pagar por valor de "%s"'
                                  ) % (slip.number, line.total))

                        name = _('Pago nómina %s') % (slip.employee_id.name)
                        payment = {
                            'payment_type': 'outbound',
                            'payment_date': slip.date_payment,
                            'partner_type': 'supplier',
                            'partner_id': slip.employee_id.address_home_id.id,
                            'communication': 'Pago nómina ' + slip.number,
                            'journal_id': slip.journal_voucher_id.id,
                            'amount': line.total,
                            'payment_method_id': 1,
                            'epago': False,
                        }

                        if slip.payment_id:
                            if slip.payment_id.state in [
                                    'posted', 'reconciled'
                            ]:
                                raise UserError(
                                    _('La nómina "%s" tiene asociado el egreso "%s" validado. Debe estar en borrador o anulado'
                                      ) % (slip.number, slip.payment_id.name))

                            if slip.payment_id.state == 'cancel':
                                slip.payment_id.action_draft()

                            slip.payment_id.write(payment)
                            payment_id = slip.payment_id

                        else:
                            payment_id = self.env['account.payment'].create(
                                payment)

                        payment_id.post()

                        # modifica la cuenta por la cuenta por pagar de salarios
                        for lin in payment_id.move_line_ids:
                            if lin.debit != 0:
                                move = lin.move_id
                                line_id = line

                                if lin.move_id.state == 'posted':
                                    lin.move_id.button_cancel()

                                lin.write({
                                    'account_id':
                                    slip.journal_id.default_credit_account_id.
                                    id
                                })
                                lin.move_id.post()
                                lines2rec = lin

                                # Hace la conciliacion de la cuenta por pagar y el egreso
                                total = 0.0
                                for mov in lines:
                                    lines2rec += mov
                                    total = total + mov.credit

                                if len(lines2rec) > 2:
                                    raise UserError(
                                        _('La nómina "%s" presenta más de una contabilización!'
                                          ) % (slip.number))

                                diff = line.total - total
                                if diff != 0.0:
                                    raise UserError(
                                        _('La nómina "%s" presenta una diferencia al conciliar de "%s"'
                                          ) % (slip.number, diff))

                                lines2rec.reconcile()

        return self.write({
            'move_bank_id': move.id,
            'payment_id': payment_id.id,
            'move_bank_name': payment_id.name,
            'state': 'paid'
        })

    @api.model
    def get_contract(self, employee, date_from, date_to):
        print('*** get_contract Sobreescrito')
        """
        @param employee: recordset of employee
        @param date_from: date field
        @param date_to: date field
        @return: returns the ids of all the contracts for the given employee that need to be considered for the given dates
        """
        # a contract is valid if it ends between the given dates
        clause_1 = [
            '&', ('date_end', '<=', date_to), ('date_end', '>=', date_from)
        ]
        # OR if it starts between the given dates
        clause_2 = [
            '&', ('date_start', '<=', date_to), ('date_start', '>=', date_from)
        ]
        # OR if it starts before the date_from and finish after the date_end (or never finish)
        clause_3 = [
            '&', ('date_start', '<=', date_from), '|',
            ('date_end', '=', False), ('date_end', '>=', date_to)
        ]
        #clause_final = [('employee_id', '=', employee.id), ('state', '=', 'open'), '|', '|'] + clause_1 + clause_2 + clause_3
        clause_final = [('employee_id', '=', employee.id),
                        ('state', 'in', ('open', 'cancel')), '|', '|'
                        ] + clause_1 + clause_2 + clause_3

        return self.env['hr.contract'].search(clause_final).ids

    @api.multi
    def compute_sheet(self):
        print('** compute_sheet en hr_payroll_co')
        for payslip in self:
            number = payslip.number or self.env['ir.sequence'].next_by_code(
                'salary.slip')
            # delete old payslip lines
            payslip.line_ids.unlink()
            payslip.worked_days_line_ids.unlink()
            payslip.input_line_ids.unlink()

            for att in self.env['ir.attachment'].sudo().search([('res_id', '=',
                                                                 payslip.id)]):
                att.unlink()

            limpiar_lineas()

            # set the list of contract for which the rules have to be applied
            # if we don't give the contract, then the rules to apply should be for all current contracts of the employee
            contract_ids = payslip.contract_id.ids or \
                payslip.get_contract(payslip.employee_id, payslip.date_from, payslip.date_to)

            #computation of the salary input
            contracts = payslip.env['hr.contract'].browse(contract_ids)

            #Revisa que la fecha de inicio no sea menor que la de inicio del contrato
            day_start = contracts.date_start
            if not day_start:
                raise UserError(
                    _('La nómina de "%s" no presenta un contrato con fecha de inicio o no está activo'
                      ) % (payslip.employee_id.name))

            if payslip.date_from < day_start:
                payslip.date_from = day_start

            worked_days_line_ids = [
                (0, 0, day) for day in payslip.get_worked_day_lines(
                    contracts, payslip.date_from.strftime('%Y-%m-%d'),
                    payslip.date_to.strftime('%Y-%m-%d'))
            ]
            input_line_ids = [(0, 0, intput) for intput in payslip.get_inputs(
                contracts, payslip.date_from, payslip.date_to)]

            payslip.write({
                'worked_days_line_ids': worked_days_line_ids,
                'input_line_ids': input_line_ids
            })

            lines = [(0, 0, line) for line in payslip._get_payslip_lines(
                contract_ids, payslip.id)]

            payslip.write({'line_ids': lines, 'number': number})

            # self.env['hr.contract'].create_report_sheet(payslip)

        return True

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = []
        structure_ids = []
        structure_ids = contracts.get_all_structures()
        rule_ids = self.env['hr.payroll.structure'].browse(
            structure_ids).get_all_rules()
        sorted_rule_ids = [
            id for id, sequence in sorted(rule_ids, key=lambda x: x[1])
        ]
        inputs = self.env['hr.salary.rule'].browse(sorted_rule_ids).mapped(
            'input_ids')

        for contract in contracts:
            if inputs:
                for input in inputs:
                    amount = 0.0
                    deduction_ids = self.env['hr.contract.deduction'].search([
                        '&', ('contract_id', '=', contract.id),
                        ('input_id', '=', input.id)
                    ])
                    ded_id = False
                    if deduction_ids:
                        for reg in deduction_ids:
                            if reg.period == 'limited':
                                if reg.current_balance <= 0.0:
                                    amount = 0.0
                                else:
                                    amount = amount + reg.amount
                            else:
                                amount = amount + reg.amount
                            ded_id = reg.id

                    input_data = {
                        'name': input.name,
                        'code': input.code,
                        'contract_id': contract.id,
                        'amount': amount,
                        'salary_rule_id': input.input_id.id,
                        'deduction_id': ded_id,
                    }
                    res += [input_data]

        return res

    @api.model
    def get_inputs_analytics(self, contracts, date_from, date_to):
        #print('*** get_inputs_analytics')
        res = []
        contract_obj = self.env['hr.contract']
        rule_obj = self.env['hr.salary.rule']
        news_obj = self.env['hr.payroll.news']

        structure_ids = contract_obj.get_all_structures()
        rule_ids = self.pool.get('hr.payroll.structure').get_all_rules(
            structure_ids)
        sorted_rule_ids = [
            id for id, sequence in sorted(rule_ids, key=lambda x: x[1])
        ]
        day_from = datetime.strptime(date_from, "%Y-%m-%d")
        day_to = datetime.strptime(date_to, "%Y-%m-%d")

        for contract in contracts:
            for rule in rule_obj.browse(sorted_rule_ids):
                if rule.input_ids:
                    for input in rule.input_ids:
                        amount = 0.0
                        #Busca el total en las novedades
                        distribuir = False
                        #news_ids = news_obj.search([('identification_id', '=',contract.employee_id.identification_id),('code','=',input.code),('date_from','=',date_from),('date_to','=',date_to),('value','!=',0)])
                        news_ids = news_obj.search([
                            ('employee_id', '=', contract.employee_id.id),
                            ('input_id', '=', input.id),
                            ('date_from', '=', date_from),
                            ('date_to', '=', date_to), ('value', '!=', 0)
                        ])
                        if news_ids:
                            for nov in news_obj.browse(news_ids):
                                amount = amount + nov.value
                                if nov.account_analytic_id:
                                    distribuir = True

                        if distribuir:
                            acumulado = 0.0
                            registro = 1
                            #print 'amount ',amount
                            #news_ids = news_obj.search(cr, uid, [('identification_id', '=',contract.employee_id.identification_id),('code','=',input.code),('date_from','=',date_from),('date_to','=',date_to),('account_analytic_id','!=',False),('value','!=',0)], context=context)
                            news_ids = news_obj.search([
                                ('employee_id', '=', contract.employee_id.id),
                                ('input_id', '=', input.id),
                                ('date_from', '=', date_from),
                                ('date_to', '=', date_to),
                                ('account_analytic_id', '!=', False),
                                ('value', '!=', 0)
                            ])
                            for nov in news_obj.browse(news_ids):
                                if len(news_ids) == registro:
                                    #Si está en el último registro se coloca el saldo
                                    porcentaje = 100 - acumulado
                                else:
                                    if amount != 0:
                                        porcentaje = round(
                                            (nov.value / amount) * 100, 2)
                                    else:
                                        porcentaje = 0
                                acumulado = acumulado + porcentaje

                                #inserta el registro
                                input_analytic = {
                                    'salary_rule_id':
                                    rule.id,
                                    'account_analytic_id':
                                    nov.account_analytic_id.id,
                                    'percent':
                                    porcentaje,
                                }
                                res += [input_analytic]
                                registro += 1

        return res

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        worked_day_lines = super(HrPayslip, self).get_worked_day_lines(
            contracts, date_from, date_to
        )
        day_from = datetime.combine(fields.Date.from_string(date_from), time.min)
        day_to = datetime.combine(fields.Date.from_string(date_to), time.max)
        days_add = 0

        if day_to.month in (1, 3, 5, 7, 8, 10, 12) and day_to.day == 31:
            days_add = -1

        if day_to.month == 2:
            if day_to.day == 28:
                days_add = 2
            if day_to.day == 29:
                days_add = 1

        for i, line in enumerate(worked_day_lines):
            if line.get("code") == "WORK100" and self.type_liquid in ["otro"]:
                worked_day_lines[i]["number_of_days"] = 0
                worked_day_lines[i]["number_of_hours"] = 0
            elif line.get("code") == "WORK100" and line.get("number_of_days") > 0:
                worked_day_lines[i]["number_of_days"] += days_add

                if day_to.month != 2:
                    return worked_day_lines

            if line.get("code") == "WORK100":
                break

        for contract in contracts.filtered(
            lambda contract: contract.resource_calendar_id
        ):
            day_leave_intervals = contract.employee_id.list_leaves(
                day_from, day_to, calendar=contract.resource_calendar_id
            )

            for day, hours, leave in day_leave_intervals:
                if day.day == day_to.day:
                    holiday = leave[:1].holiday_id

                    for i, line in enumerate(worked_day_lines):
                        if line.get("code") == (
                            holiday.holiday_status_id.name or "GLOBAL"
                        ):
                            worked_day_lines[i]["number_of_days"] += days_add

                    break

        return worked_day_lines

    @api.multi
    def onchange_employee_id(self,
                             date_from,
                             date_to,
                             employee_id=False,
                             contract_id=False):
        print('** onchange_employee_id sobreescrito')
        #defaults
        res = {
            'value': {
                'line_ids': [],
                #delete old input lines
                'input_line_ids': [(
                    2,
                    x,
                ) for x in self.input_line_ids.ids],
                #delete old worked days lines
                'worked_days_line_ids': [(
                    2,
                    x,
                ) for x in self.worked_days_line_ids.ids],
                #'details_by_salary_head':[], TODO put me back
                'name':
                '',
                'contract_id':
                False,
                'struct_id':
                False,
            }
        }
        if (not employee_id) or (not date_from) or (not date_to):
            return res
        ttyme = datetime.combine(fields.Date.from_string(date_from), time.min)
        employee = self.env['hr.employee'].browse(employee_id)
        locale = self.env.context.get('lang') or 'en_US'
        res['value'].update({
            'name':
            _('Salary Slip of %s for %s') %
            (employee.name,
             tools.ustr(
                 babel.dates.format_date(
                     date=ttyme, format='MMMM-y', locale=locale))),
            'company_id':
            employee.company_id.id,
        })

        if not self.env.context.get('contract'):
            #fill with the first contract of the employee
            contract_ids = self.get_contract(employee, date_from, date_to)
        else:
            if contract_id:
                #set the list of contract for which the input have to be filled
                contract_ids = [contract_id]
            else:
                #if we don't give the contract, then the input to fill should be for all current contracts of the employee
                contract_ids = self.get_contract(employee, date_from, date_to)

        if not contract_ids:
            return res
        contract = self.env['hr.contract'].browse(contract_ids[0])

        #Revisa que la fecha de inicio no sea menor que la de inicio del contrato
        day_start = contract.date_start
        if date_from < day_start:
            date_from = day_start

            res['value'].update({'date_from': day_start})

        res['value'].update({'contract_id': contract.id})
        struct = contract.struct_id
        if not struct:
            return res
        res['value'].update({
            'struct_id': struct.id,
        })
        #computation of the salary input
        contracts = self.env['hr.contract'].browse(contract_ids)
        worked_days_line_ids = self.get_worked_day_lines(
            contracts, date_from, date_to)
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        res['value'].update({
            'worked_days_line_ids': worked_days_line_ids,
            'input_line_ids': input_line_ids,
        })
        return res

    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict,
                                                      category.parent_id,
                                                      amount)
            localdict['categories'].dict[
                category.code] = category.code in localdict[
                    'categories'].dict and localdict['categories'].dict[
                        category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute(
                    """
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute(
                    """
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute(
                    """SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_mount(self, code, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category hc WHERE hp.id = pl.slip_id AND pl.category_id = hc.id AND hp.contract_id = %s AND hp.date_from >= (to_char(%s::date,'YYYY-mm')||'-01')::date\
                                  AND hp.date_to <= (to_char(%s::date,'YYYY-mm-dd'))::date AND hc.code = %s",
                    (self.contract_id.id, from_date, to_date, code))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_mount_inicial(self, code, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category hc WHERE hp.id = pl.slip_id AND pl.category_id = hc.id AND hp.contract_id = %s AND hp.date_from between (to_char(%s::date,'YYYY-mm-dd'))::date\
                                  AND (to_char(%s::date,'YYYY-mm-dd'))::date AND hc.code = %s",
                    (self.contract_id.id, from_date, to_date, code))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_mount_before(self, code, from_date):
                #suma una regla salaria por categoria
                #date_start = datetime.strptime(from_date,"%Y-%m-%d")
                date_start = from_date
                mes = date_start.month - 1
                ano = date_start.year
                if mes == 0:
                    mes = 12
                    ano = ano = date_start.year - 1

                from_date = str(ano) + '-' + str(mes) + '-01'

                if mes == 2:
                    dia = 28
                else:
                    dia = 30

                to_date = str(ano) + '-' + str(mes) + '-' + str(dia)

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category hc WHERE hp.id = pl.slip_id AND pl.category_id = hc.id AND hp.contract_id = %s AND hp.date_from >= %s::date\
                                  AND hp.date_to <= %s::date AND hc.code = %s",
                    (self.contract_id.id, from_date, to_date, code))

                res = self.env.cr.fetchone()
                valor = res and res[0] or 0.0

                return res and res[0] or 0.0

            def sum_rule_before(self, code, from_date):
                #suma una regla salarial del mes anterior
                #date_start = datetime.strptime(from_date,"%Y-%m-%d")
                date_start = from_date
                mes = date_start.month - 1
                ano = date_start.year
                if mes == 0:
                    mes = 12
                    ano = ano = date_start.year - 1

                from_date = str(ano) + '-' + str(mes) + '-01'

                if mes == 2:
                    dia = 28
                else:
                    dia = 30

                stop_date = str(ano) + '-' + str(mes) + '-' + str(dia)
                start_date = str(ano) + '-' + str(mes) + '-' + '01'

                self.env.cr.execute(
                    """SELECT COALESCE(sum(pl.total),0) as suma 
                                   FROM hr_payslip_line as pl  
                                   inner join hr_payslip as hp on (hp.id = pl.slip_id)                                    
                                   inner join hr_salary_rule r on (r.id = pl.salary_rule_id)
                                   WHERE hp.contract_id = %(contrato)s 
                                   AND hp.date_from between %(fecha_desde)s::date and %(fecha_hasta)s::date
                                   AND r.code = %(regla)s""", {
                        'contrato': self.contract_id.id,
                        'fecha_desde': start_date,
                        'fecha_hasta': stop_date,
                        'regla': code,
                    })
                res = self.env.cr.fetchone()
                valor = res and res[0] or 0.0

                #Suma tambien los acumulados
                self.env.cr.execute(
                    """select coalesce(sum(a.amount),0) as suma
                         from hr_contract_acumulados a
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and a.contract_id = %(contrato)s
                           and r.code = %(regla)s
                           and a.date between %(fecha_desde)s::date and %(fecha_hasta)s::date
                         """, {
                        'contrato': self.contract_id.id,
                        'fecha_desde': start_date,
                        'fecha_hasta': stop_date,
                        'regla': code,
                    })
                res = self.env.cr.fetchone()
                valor = valor + (res and res[0] or 0.0)

                return valor

            @api.multi
            def get_auxtransporte_ano(self, from_date):
                date_start = from_date
                ano = date_start.year

                from_date = str(ano) + '-01-01'
                to_date = str(ano) + '-12-31'

                self.env.cr.execute(
                    "select sub_transport from account_fiscal_year where date_from = %s::date and date_to = %s::date",
                    (from_date, to_date))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            @api.multi
            def get_minsalary_ano(self, from_date):
                #date_start = datetime.strptime(from_date,"%Y-%m-%d")
                date_start = from_date
                ano = date_start.year

                from_date = str(ano) + '-01-01'
                to_date = str(ano) + '-12-31'

                self.env.cr.execute(
                    "select minimum_wage from account_fiscal_year where date_from = %s::date and date_to = %s::date",
                    (from_date, to_date))

                res = self.env.cr.fetchone()
                valor = res and res[0] or 0.0
                salario = res and res[0] or 0.0

                return res and res[0] or 0.0

            def sum_rule(self, rule_id, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category hc WHERE hp.id = pl.slip_id AND pl.category_id = hc.id AND hp.contract_id = %s AND hp.date_from >= (to_char(%s::date,'YYYY-mm')||'-01')::date\
                                  AND hp.date_to <= (to_char(%s::date,'YYYY-mm')||'-15')::date AND pl.salary_rule_id = %s",
                    (self.contract_id.id, from_date, to_date, rule_id))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_rule_inicial(self, rule_id, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category hc WHERE hp.id = pl.slip_id AND pl.category_id = hc.id AND hp.contract_id = %s AND hp.date_from between (to_char(%s::date,'YYYY-mm-dd'))::date\
                                  AND (to_char(%s::date,'YYYY-mm-dd'))::date AND pl.salary_rule_id = %s",
                    (self.contract_id.id, from_date, to_date, rule_id))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_rule_range_acumulados(self, code, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    """select sum(a.amount) 
                              from hr_contract_acumulados a
                              inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                              where r.code = %(regla)s
                                and a.contract_id = %(contrato)s
                                and p.special = False
                                and a.date between %(from_date)s::date and %(to_date)s::date
                                ''""", {
                        'contrato': self.contract_id.id,
                        'fecha_inicial': from_date,
                        'fecha_final': to_date,
                        'regla': code,
                    })
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_rule_range(self, code, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule sr WHERE hp.id = pl.slip_id AND pl.salary_rule_id = sr.id AND hp.contract_id = %s AND %s::date between hp.date_from\
                                  AND hp.date_to AND sr.code = %s",
                    (self.contract_id.id, from_date, code))

                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_rule_discount(self, code, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                "Esta funciona tiene como objetivo determinar si se realiza o no un descuento, especial para cuando el empleado sale a vacaciones"
                self.env.cr.execute(
                    "SELECT COALESCE(sum(pl.total),0) as suma FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule sr WHERE hp.id = pl.slip_id AND pl.salary_rule_id = sr.id AND hp.contract_id = %s AND %s::date between hp.date_from\
                                  AND hp.date_to AND sr.code = %s",
                    (self.contract_id.id, from_date, code))
                res = self.env.cr.fetchone()
                valor = res and res[0] or 0.0

                if valor != 0.0:
                    self.env.cr.execute(
                        "SELECT hp.date_from as fecha FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule sr WHERE hp.id = pl.slip_id AND pl.salary_rule_id = sr.id AND hp.contract_id = %s AND %s::date between hp.date_from\
                                  AND hp.date_to AND sr.code = %s",
                        (self.contract_id.id, from_date, code))
                    fecha = self.env.cr.fetchone()[0] or False

                    if fecha:
                        date_from_discount = datetime.strptime(
                            fecha, "%Y-%m-%d")
                        date_from_nomina = datetime.strptime(
                            from_date, "%Y-%m-%d")

                        if date_from_discount.month != date_from_nomina.month:
                            valor = 0.0

                return valor

            def sum_days(self, from_date, to_date):
                from_date = from_date.strftime("%Y-%m-%d")
                to_date = to_date.strftime("%Y-%m-%d")

                self.env.cr.execute(
                    "SELECT coalesce(sum(number_of_days),0) as dias from hr_payslip_worked_days hd, hr_payslip as hp where hd.code in ('WORK100','VACACIONES_REMUNERADAS') AND hp.id = hd.payslip_id AND hp.contract_id = %s AND hp.date_from between (to_char(%s::date,'YYYY-mm')||'-01')::date\
                                  AND (to_char(%s::date,'YYYY-mm-dd'))::date",
                    (self.contract_id.id, from_date, to_date))

                res = self.env.cr.fetchone()

                return res and res[0] or 0

            def day(self, date_from):
                """
                Funcion que retorna el dia de la fecha recibida como parametro
                """
                res = False
                if date_from:
                    #day_from = datetime.strptime(date_from,"%Y-%m-%d")
                    day_from = date_from
                    return day_from.day
                return res

            def month(self, date_from):
                """
                Funcion que retorna el dia de la fecha recibida como parametro
                """
                res = False
                if date_from:
                    #day_from = datetime.strptime(date_from,"%Y-%m-%d")
                    day_from = date_from
                    return day_from.month
                return res

            def days_between(self, start_date, end_date):
                start_date = start_date.strftime("%Y-%m-%d")
                end_date = end_date.strftime("%Y-%m-%d")

                #s1, e1 =  start_date , end_date + timedelta(days=1)
                s1, e1 = datetime.strptime(
                    start_date, "%Y-%m-%d"), datetime.strptime(
                        end_date, "%Y-%m-%d") + timedelta(days=1)
                #Convert to 360 days
                s360 = (s1.year * 12 + s1.month) * 30 + s1.day
                e360 = (e1.year * 12 + e1.month) * 30 + e1.day
                res = divmod(e360 - s360, 30)
                dias = ((res[0] * 30) + res[1]) or 0
                return dias

        #--------------------------------------
        #we keep a dict with the result because a value can be overwritten by another rule with the same code
        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        fiscal = self.env['account.fiscal.year'].search([('state', '=',
                                                          'draft')])
        payslip = self.env['hr.payslip'].browse(payslip_id)
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict,
                                 self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        baselocaldict = {
            'categories': categories,
            'rules': rules,
            'payslip': payslips,
            'worked_days': worked_days,
            'inputs': inputs,
            'fiscal': fiscal
        }
        #get the ids of the structures on the contracts and their parent id as well
        contracts = self.env['hr.contract'].browse(contract_ids)

        #dependiendo del tipo de nomina toma las estructuras salariales
        structure_ids = []
        if payslip.type_liquid in ('nomina', 'nomi_otro'):
            if len(contracts) == 1 and payslip.struct_id:
                structure_ids = list(
                    set(payslip.struct_id._get_parent_structure().ids))
            else:
                structure_ids = contracts.get_all_structures()

        if payslip.type_liquid in ('otro',
                                   'nomi_otro') and payslip.struct_liquida_id:
            structure_ids += payslip.get_all_structures()

        #get the rules of the structure and thier children
        rule_ids = self.env['hr.payroll.structure'].browse(
            structure_ids).get_all_rules()
        #run the rules by sequence
        sorted_rule_ids = [
            id for id, sequence in sorted(rule_ids, key=lambda x: x[1])
        ]
        sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)

        for contract in contracts:
            employee = contract.employee_id
            localdict = dict(baselocaldict,
                             employee=employee,
                             contract=contract)
            for rule in sorted_rules:
                key = rule.code + '-' + str(contract.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                #check if the rule can be applied
                if rule._satisfy_condition(
                        localdict) and rule.id not in blacklist:
                    #compute the amount of the rule
                    amount, qty, rate = rule._compute_rule(localdict)
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[
                        rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = amount * qty * rate / 100.0
                    localdict[rule.code] = tot_rule
                    rules_dict[rule.code] = rule
                    #sum the amount for its salary category
                    localdict = _sum_salary_rule_category(
                        localdict, rule.category_id,
                        tot_rule - previous_amount)
                    #create/overwrite the rule in the temporary results
                    #Solo guarda los que tiene valor
                    if amount != 0:
                        result_dict[key] = {
                            'salary_rule_id': rule.id,
                            'contract_id': contract.id,
                            'name': rule.name,
                            'code': rule.code,
                            'category_id': rule.category_id.id,
                            'sequence': rule.sequence,
                            'appears_on_payslip': rule.appears_on_payslip,
                            'condition_select': rule.condition_select,
                            'condition_python': rule.condition_python,
                            'condition_range': rule.condition_range,
                            'condition_range_min': rule.condition_range_min,
                            'condition_range_max': rule.condition_range_max,
                            'amount_select': rule.amount_select,
                            'amount_fix': rule.amount_fix,
                            'amount_python_compute':
                            rule.amount_python_compute,
                            'amount_percentage': rule.amount_percentage,
                            'amount_percentage_base':
                            rule.amount_percentage_base,
                            'register_id': rule.register_id.id,
                            'type': rule.type,
                            'amount': amount,
                            'employee_id': contract.employee_id.id,
                            'quantity': qty,
                            'rate': rate,
                        }
                else:
                    #blacklist this rule and its children
                    blacklist += [
                        id for id, seq in rule._recursive_search_of_rules()
                    ]

        return list(result_dict.values())

    @api.multi
    def get_xls_file(self):
        """
        Funcion para descargar el xls 
        """
        filename = self.number.replace('/', '-') + '.xlsx'
        xls_attachment = self.env['ir.attachment'].sudo().search([
            ('datas_fname', '=', filename), ('res_id', '=', self.id)
        ])

        if not xls_attachment:
            raise ValidationError(
                'No ha generado el archivo Excel. Depronto no existen reglas salariales que generen detalle del cálculo'
            )

        return {
            'type': 'ir.actions.act_url',
            'url': '/download/xls/payslip/{}'.format(self.id),
            'target': 'self'
        }
