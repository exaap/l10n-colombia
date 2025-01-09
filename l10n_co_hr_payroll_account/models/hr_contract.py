# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).
from datetime import timedelta
import base64
import pandas as pd
from odoo import fields, models, api, tools, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError

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


def days_between(start_date, end_date):
    # Add 1 day to end date to solve different last days of month
    # s1, e1 =  datetime.strptime(start_date,"%Y-%m-%d") , datetime.strptime(end_date,"%Y-%m-%d")  + timedelta(days=1)
    s1, e1 = start_date, end_date + timedelta(days=1)
    # Convert to 360 days
    s360 = (s1.year * 12 + s1.month) * 30 + s1.day
    e360 = (e1.year * 12 + e1.month) * 30 + e1.day
    # Count days between the two 360 dates and return tuple (months, days)
    res = divmod(e360 - s360, 30)
    return ((res[0] * 30) + res[1]) or 0


class HrContract(models.Model):
    _inherit = 'hr.contract'

    analytic_ids = fields.One2many(comodel_name='hr.contract.analytic',
                                   inverse_name='contract_id',
                                   string='Analityc Account')

    setting_ids = fields.One2many(comodel_name='hr.contract.setting',
                                  inverse_name='contract_id',
                                  string='Configuratión')
    deduction_ids = fields.One2many(comodel_name='hr.contract.deduction',
                                    inverse_name='contract_id',
                                    string='Deductions')
    liquidation_ids = fields.One2many(comodel_name='hr.contract.liquidation',
                                      inverse_name='contract_id',
                                      string='liquidation')
    accumulated_ids = fields.One2many(comodel_name='hr.contract.accumulated',
                                      inverse_name='contract_id',
                                      string='Accumulated')
    change_wage_ids = fields.One2many(comodel_name='hr.contract.change.wage',
                                      inverse_name='contract_id',
                                      string='Salary changes')
    risk_id = fields.Many2one(comodel_name='hr.contract.risk',
                              required=True,
                              string='Professional risk')
    date_bunus = fields.Date(string='Bunus liquidation date')
    date_layoff_fund = fields.Date(string='Date Layoff Fund')
    date_holidays = fields.Date(string='Holiday liquidation date')
    date_liquidation = fields.Date(string="Contract liquidation date")
    distribute = fields.Boolean(
        string='Distribute by analytical account',
        default=False,
        help=
        "Indicates if when calculating the contract payroll it is distributed by cost center"
    )
    factor = fields.Float(string='Salary factor', required=True, default=0.0)
    parcial = fields.Boolean(string='Part time', default=False)
    pensionary = fields.Boolean(string='Pensionary', default=False)
    integral = fields.Boolean(string='integral salary', default=False)
    condition = fields.Float(string='Previous condition',
                             default=0.0,
                             digits=dp.get_precision('Payroll'))
    compensation = fields.Float(string='Compensation',
                                default=0.0,
                                digits=dp.get_precision('Payroll'))
    date_to = fields.Date(string="Fixed contract termination")

    register_ids = fields.One2many(string='Contribution Registers',
                                   comodel_name='hr.contract.register',
                                   inverse_name='contract_id')

    @api.model
    def promedio_prima(self, contract_id, payslip_detail, proyectado=False):
        print('########################## promedio_prima')
        result = 0.0

        if payslip_detail.days_neto > 0:
            # Busca las incapacidades en el mismo rango de fechas
            self.env.cr.execute(
                """select coalesce(sum(h.number_of_days),0) 
                           from hr_leave h
                           inner join hr_leave_type s on (s.id = h.holiday_status_id)
                           where h.employee_id = %(empleado)s
                             and h.request_date_from::date >= %(fecha_inicial)s::date
                             and h.request_date_to::date <= %(fecha_final)s::date
                             and s.unpaid = True
                             and h.state = 'validate'""", {
                    'empleado': contract_id.employee_id.id,
                    'fecha_inicial': payslip_detail.date_from,
                    'fecha_final': payslip_detail.date_to,
                })

            # Revisa si en los ultimos 6 meses ha cambiado el salario
            self.env.cr.execute(
                """select coalesce(sum(wage),0)/( case when count(*)=0 then 1 else count(*) end  )
                          from hr_contract_change_wage
                          where contract_id = %(contrato)s
                          and date_start >= (SELECT (date_trunc('month', TIMESTAMP %(fecha)s) - interval '5 month')::date)
                          """, {
                    'contrato': contract_id.id,
                    'fecha': payslip_detail.date_to
                })
            wage = self.env.cr.fetchone()[0] or 0.0
            print('Promedio 6 meses ', wage)
            print('Salario basico actual ', contract_id.wage)
            payslip_detail.wage_actual = contract_id.wage

            if 1 == 1:
                print('Calcula acumulados para promedio salarial')
                #Si es proyectdo toma los acumulados desde el mes anterior
                if proyectado:
                    mes_anterior = 1
                else:
                    mes_anterior = 0

                self.env.cr.execute(
                    """select round(sum(a.salario)::numeric) total
                          from (
                          select
                             s.contract_id as contract_id,
                             l.total as salario
                          from hr_payslip_line l
                          inner join hr_payslip s on (s.id = l.slip_id)
                          inner join hr_employee e on (e.id = l.employee_id) 
                          inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                          where l.total <> 0
                            and s.contract_id = %(contrato)s
                            and r.promedio = True
                            and s.date_from between %(fecha_prima)s::date and (%(fecha_liquidacion)s::date - interval '%(mes_anterior)s month')::date
                         union all
                         select 
                            c.id as contract_id,
                            a.amount as salario
                         from hr_contract_acumulados a
                         inner join hr_contract c on (c.id = a.contract_id)
                         inner join hr_employee e on (e.id = c.employee_id)
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and c.id = %(contrato)s
                           and r.promedio = True
                           and a.date between %(fecha_prima)s::date and (%(fecha_liquidacion)s::date - interval '%(mes_anterior)s month')::date                       
                         ) as a
                         group by a.contract_id""", {
                        'contrato': contract_id.id,
                        'fecha_prima': payslip_detail.date_from,
                        'fecha_liquidacion': payslip_detail.date_to,
                        'mes_anterior': mes_anterior,
                    })
                res = self.env.cr.fetchone()
                if res:
                    total_salario = res[0] or 0.0
                else:
                    total_salario = 0.0

                payslip_detail.wage_total += total_salario

                print('total salario acumulado', total_salario)

                #Si es proyectado se suma un mes con el salario basico
                if proyectado:
                    payslip_detail.wage_total += contract_id.wage

            #Calcula el salario promedio dependiendo si ha cambiado en lo ultimos 3 meses
            if wage == contract_id.wage or wage == 0.0:
                print('salario actual no cambio en 3 meses ', contract_id.wage)
                payslip_detail.wage_average = contract_id.wage + contract_id.factor
            else:
                if payslip_detail.days_neto != 0:
                    payslip_detail.wage_average = (
                        payslip_detail.wage_total /
                        payslip_detail.days_neto) * 30
                else:
                    raise UserError(_('Error!'),
                                    _("Existe una division por cero"))

            print('salario promedio ', payslip_detail.wage_average)

            #------Busca los acumulados incluyendo el recibido por parametro
            print('Busca los acumulados para otros devengados')
            self.env.cr.execute(
                """
                          select
                             s.date_from as date,
                             coalesce(s.number,'') as number,
                             coalesce(r.name,'') as salary_rule,
                             l.total as amount
                          from hr_payslip_line l
                          inner join hr_payslip s on (s.id = l.slip_id)
                          inner join hr_employee e on (e.id = l.employee_id) 
                          inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                          where l.total <> 0
                            and s.contract_id = %(contrato)s
                            and r.prima = True
                            and s.date_from between %(fecha_prima)s::date and %(fecha_liquidacion)s::date                         
                         union all
                         select 
                            a.date as date,
                            'Acumulado' as number,
                            coalesce(r.name,'') as salary_rule,
                            a.amount as amount
                         from hr_contract_acumulados a
                         inner join hr_contract c on (c.id = a.contract_id)
                         inner join hr_employee e on (e.id = c.employee_id)
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and c.id = %(contrato)s
                           and r.prima = True                           
                           and a.date between %(fecha_prima)s::date and %(fecha_liquidacion)s::date                         
                         """, {
                    'contrato': contract_id.id,
                    'fecha_prima': payslip_detail.date_from,
                    'fecha_liquidacion': payslip_detail.date_to,
                })

            res = self.env.cr.fetchone()
            total = 0
            if res:
                grabar_datos(res)
                for result in res:
                    total += result[3]

            print('total ', total)
            payslip_detail.variable_total += total

            if payslip_detail.days_neto < 30:
                payslip_detail.variable_average = payslip_detail.variable_total
            else:
                payslip_detail.variable_average = (
                    (payslip_detail.variable_total) /
                    payslip_detail.days_neto) * 30

            resultado = payslip_detail.wage_average + payslip_detail.variable_average

        return resultado

    @api.model
    def calcular_prima(self,
                       date_liquidacion,
                       date_prima,
                       contract_id,
                       amount=0.0,
                       proyectado=False,
                       amount_salary=0.0,
                       payslip=None,
                       salary_code=None):
        print('############## calcular_prima')
        #Elimina calculos previos
        year_id = self.env['account.fiscalyear'].search([
            ('date_start', '<=', date_liquidacion),
            ('date_stop', '>=', date_liquidacion)
        ])

        unlink_ids = self.env['hr.contract.liquidacion'].search([
            ('contract_id', '=', self.id), ('sequence', '=', '1')
        ])
        if unlink_ids:
            for liq in unlink_ids:
                liq.unlink()

        #elimina el detalle previo
        salary_rule = self.env['hr.salary.rule'].search([('code', '=',
                                                          salary_code)])
        details_ids = self.env['hr.payslip.details'].search([
            ('slip_id', '=', payslip.id),
            ('salary_rule_id', '=', salary_rule.id)
        ])
        if details_ids:
            for detail in details_ids:
                detail.unlink()

        for cont in self:

            #------------  PRIMA ------------------

            #valida fecha de liquidacion de contrato
            if not date_liquidacion:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de contrato"))

            #la fecha de liquidacion debe ser mayor que la de inicio de contrato
            day_start = cont.date_start
            day_end = date_liquidacion

            if (day_end - day_start).days <= 0:
                raise UserError(
                    _('Error!'),
                    _("La fecha de liquidación de contrato debe ser mayor a la fecha de inicio del mismo"
                      ))

            #calcula prima
            if not date_prima:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de prima"))

            #la fecha de liquidacion prima debe ser mayor que la de inicio de contrato
            day_to = date_prima
            if (day_to - day_start).days < 0:
                day_to = day_start
                #raise UserError(_('Error!'),_("La fecha de liquidación de prima debe ser mayor a la fecha de inicio del contrato"))

            dias = days_between(day_to, day_end)
            print('dias totales ', dias)

            payslip_detail = self.env['hr.payslip.details'].create({
                'slip_id':
                payslip.id,
                'salary_rule_id':
                salary_rule.id,
                'date_from':
                day_to,
                'date_to':
                day_end,
                'days_total':
                dias,
                'wage_total':
                amount_salary,
                'variable_total':
                amount,
            })

            # Busca las incapacidades en el mismo rango de fechas
            self.env.cr.execute(
                """select coalesce(sum(h.number_of_days),0) 
                           from hr_leave h
                           inner join hr_leave_type s on (s.id = h.holiday_status_id)
                           where h.employee_id = %(empleado)s
                             and h.request_date_from::date >= %(fecha_inicial)s::date
                             and h.request_date_to::date <= %(fecha_final)s::date
                             and s.unpaid = True
                             and h.state = 'validate'""", {
                    'empleado': contract_id.employee_id.id,
                    'fecha_inicial': date_prima,
                    'fecha_final': date_liquidacion,
                })
            ausencias = self.env.cr.fetchone()[0] or 0
            print('dias ausencias ', ausencias)
            payslip_detail.days_leave = ausencias
            dias = dias - ausencias
            payslip_detail.days_neto = dias
            print('Dias neto ', dias)

            promedio_salario_var = self.promedio_prima(contract_id,
                                                       payslip_detail,
                                                       proyectado)
            print('promedio_salario_var ', promedio_salario_var)
            grabar_linea2('Promedio salarial', promedio_salario_var)

            aux_transporte = 0.00
            if year_id:
                for ano in year_id:
                    #aux_transporte = (ano.sub_transporte /30) * dias
                    #Si gana menos de 2 salarios minimos legal vigente
                    if promedio_salario_var < ano.salario_minimo * 2:
                        aux_transporte = ano.sub_transporte

            print('Subsidio de transporte ', aux_transporte)
            grabar_linea2('Subsidio de transporte ', aux_transporte)
            payslip_detail.subsidio_transporte = aux_transporte

            base = round(aux_transporte + promedio_salario_var, 0)
            print('base ', base)
            grabar_linea2('Total base', base)
            payslip_detail.total_average = base
            grabar_linea2('Dias', dias)
            total_prima = round((base * dias) / 360, 0)
            print('total prima ', total_prima)
            grabar_linea2('Total prima', total_prima)
            payslip_detail.amount = total_prima

            print('Termina calcular prima')
            return total_prima

    def promedio_vacaciones_comercial(self, date_liquidacion, contract_id,
                                      payslip, salary_rule):
        print('***** promedio_vacaciones_comercial')
        mes_anterior = 12
        total = 0

        self.env.cr.execute(
            """
                          select
                             s.date_from as date,
                             coalesce(s.number,'') as number,
                             coalesce(r.name,'') as salary_rule,
                             l.total as amount
                          from hr_payslip_line l
                          inner join hr_payslip s on (s.id = l.slip_id)
                          inner join hr_employee e on (e.id = l.employee_id) 
                          inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                          where l.total <> 0
                            and s.contract_id = %(contrato)s
                            and r.promedio = True
                            and s.date_from between (%(fecha)s::date - interval '%(mes_anterior)s month')::date and  %(fecha)s::date
                         union all
                         select 
                            a.date as date,
                            'Acumulado' as number,
                            coalesce(r.name,'') as salary_rule,
                            a.amount as amount
                         from hr_contract_acumulados a
                         inner join hr_contract c on (c.id = a.contract_id)
                         inner join hr_employee e on (e.id = c.employee_id)
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and c.id = %(contrato)s
                           and r.promedio = True
                           and a.date between (%(fecha)s::date - interval '%(mes_anterior)s month')::date and  %(fecha)s::date                       
                         """, {
                'contrato': contract_id.id,
                'fecha': date_liquidacion,
                'mes_anterior': mes_anterior,
            })
        res = self.env.cr.fetchall()
        if res:
            grabar_datos(res)
            for result in res:
                total = total + result[3]

        return total

    @api.model
    def calcular_vacaciones(self,
                            date_liquidacion,
                            dias_vacaciones,
                            contract_id,
                            amount=0.0,
                            amount_salary=0.0,
                            payslip=None,
                            salary_code=None):
        print('############## calcular_vacaciones')

        #Elimina calculos previos
        unlink_ids = self.env['hr.contract.liquidacion'].search([
            ('contract_id', '=', self.id), ('sequence', '=', '2')
        ])
        if unlink_ids:
            for liq in unlink_ids:
                liq.unlink()

        #elimina el detalle previo
        salary_rule = self.env['hr.salary.rule'].search([('code', '=',
                                                          salary_code)])
        details_ids = self.env['hr.payslip.details'].search([
            ('slip_id', '=', payslip.id),
            ('salary_rule_id', '=', salary_rule.id)
        ])
        if details_ids:
            for detail in details_ids:
                detail.unlink()

        for cont in self:

            #------------  VACACIONES ------------------

            #valida fecha de liquidacion de contrato
            if not date_liquidacion:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de contrato"))

            #la fecha de liquidacion debe ser mayor que la de inicio de contrato
            day_start = cont.date_start
            day_end = date_liquidacion

            if (day_end - day_start).days <= 0:
                raise UserError(
                    _('Error!'),
                    _("La fecha de liquidación de contrato debe ser mayor a la fecha de inicio del mismo"
                      ))

            #la fecha de liquidacion vacaciones debe ser mayor que la de inicio de contrato
            day_to = date_liquidacion
            if (day_to - day_start).days < 0:
                day_to = day_start
                #raise UserError(_('Error!'),_("La fecha de liquidación de vacaciones debe ser mayor a la fecha de inicio del contrato"))

            payslip_detail = self.env['hr.payslip.details'].create({
                'slip_id':
                payslip.id,
                'salary_rule_id':
                salary_rule.id,
                'date_from':
                day_to,
                'date_to':
                day_end,
                'days_total':
                dias_vacaciones,
                'wage_total':
                amount_salary,
                'variable_total':
                amount,
            })

            total_salario = self.promedio_vacaciones_comercial(
                date_liquidacion,
                contract_id,
                payslip,
                salary_rule=salary_rule)
            print('total salario  ', total_salario)

            promedio_salario = round(total_salario / 12, 0)
            base = round(promedio_salario, 0)
            print('base ', base)
            grabar_linea2('Promedio salarial', base)
            grabar_linea2('Dias de vacaciones', dias_vacaciones)

            total_vacaciones = round((base / 30) * dias_vacaciones, 0)
            print('total vacaciones ', total_vacaciones)
            grabar_linea2('Total vacaciones', total_vacaciones)

            print('Dias de vacaciones', dias_vacaciones)
            payslip_detail.days_leave = 0
            payslip_detail.days_neto = dias_vacaciones
            payslip_detail.total_average = base
            payslip_detail.subsidio_transporte = 0
            payslip_detail.amount = total_vacaciones

            print('== Termina calcular vacaciones ==')
            return total_vacaciones

    @api.model
    def promedio_cesantias(self,
                           contract_id,
                           payslip_detail,
                           proyectado=False):
        print('########################## promedio_cesantias')
        result = 0.0

        if payslip_detail.days_neto > 0:
            # Busca las incapacidades en el mismo rango de fechas
            self.env.cr.execute(
                """select coalesce(sum(h.number_of_days),0) 
                           from hr_leave h
                           inner join hr_leave_type s on (s.id = h.holiday_status_id)
                           where h.employee_id = %(empleado)s
                             and h.request_date_from::date >= %(fecha_inicial)s::date
                             and h.request_date_to::date <= %(fecha_final)s::date
                             and s.unpaid = True
                             and h.state = 'validate'""", {
                    'empleado': contract_id.employee_id.id,
                    'fecha_inicial': payslip_detail.date_from,
                    'fecha_final': payslip_detail.date_to,
                })

            # Revisa si en los ultimos 6 meses ha cambiado el salario
            self.env.cr.execute(
                """select coalesce(sum(wage),0)/( case when count(*)=0 then 1 else count(*) end  )
                          from hr_contract_change_wage
                          where contract_id = %(contrato)s
                          and date_start >= (SELECT (date_trunc('month', TIMESTAMP %(fecha)s) - interval '5 month')::date)
                          """, {
                    'contrato': contract_id.id,
                    'fecha': payslip_detail.date_to
                })
            wage = self.env.cr.fetchone()[0] or 0.0
            print('Promedio 6 meses ', wage)
            print('Salario basico actual ', contract_id.wage)
            payslip_detail.wage_actual = contract_id.wage

            if 1 == 1:
                print('Calcula acumulados para promedio salarial')
                #Si es proyectdo toma los acumulados desde el mes anterior
                if proyectado:
                    mes_anterior = 1
                else:
                    mes_anterior = 0

                self.env.cr.execute(
                    """select round(sum(a.salario)::numeric) total
                          from (
                          select
                             s.contract_id as contract_id,
                             l.total as salario
                          from hr_payslip_line l
                          inner join hr_payslip s on (s.id = l.slip_id)
                          inner join hr_employee e on (e.id = l.employee_id) 
                          inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                          where l.total <> 0
                            and s.contract_id = %(contrato)s
                            and r.promedio = True
                            and s.date_from between %(fecha_prima)s::date and (%(fecha_liquidacion)s::date - interval '%(mes_anterior)s month')::date
                         union all
                         select 
                            c.id as contract_id,
                            a.amount as salario
                         from hr_contract_acumulados a
                         inner join hr_contract c on (c.id = a.contract_id)
                         inner join hr_employee e on (e.id = c.employee_id)
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and c.id = %(contrato)s
                           and r.promedio = True
                           and a.date between %(fecha_prima)s::date and (%(fecha_liquidacion)s::date - interval '%(mes_anterior)s month')::date                       
                         ) as a
                         group by a.contract_id""", {
                        'contrato': contract_id.id,
                        'fecha_prima': payslip_detail.date_from,
                        'fecha_liquidacion': payslip_detail.date_to,
                        'mes_anterior': mes_anterior,
                    })
                res = self.env.cr.fetchone()
                if res:
                    total_salario = res[0] or 0.0
                else:
                    total_salario = 0.0

                payslip_detail.wage_total += total_salario

                print('total salario acumulado', total_salario)

                #Si es proyectado se suma un mes con el salario basico
                if proyectado:
                    payslip_detail.wage_total += contract_id.wage

            #Calcula el salario promedio dependiendo si ha cambiado en lo ultimos 3 meses
            if wage == contract_id.wage or wage == 0.0:
                print('salario actual no cambio en 3 meses ', contract_id.wage)
                payslip_detail.wage_average = contract_id.wage + contract_id.factor
            else:
                if payslip_detail.days_neto != 0:
                    payslip_detail.wage_average = (
                        payslip_detail.wage_total /
                        payslip_detail.days_neto) * 30
                else:
                    raise UserError(_('Error!'),
                                    _("Existe una division por cero"))

            print('salario promedio ', payslip_detail.wage_average)

            #------Busca los acumulados incluyendo el recibido por parametro
            print('Busca los acumulados para otros devengados')
            self.env.cr.execute(
                """
                          select
                             s.date_from as date,
                             coalesce(s.number,'') as number,
                             coalesce(r.name,'') as salary_rule,
                             l.total as amount
                          from hr_payslip_line l
                          inner join hr_payslip s on (s.id = l.slip_id)
                          inner join hr_employee e on (e.id = l.employee_id) 
                          inner join hr_salary_rule r on (r.id = l.salary_rule_id)
                          where l.total <> 0
                            and s.contract_id = %(contrato)s
                            and r.cesantias = True
                            and s.date_from between %(fecha_prima)s::date and %(fecha_liquidacion)s::date                         
                         union all
                         select 
                            a.date as date,
                            'Acumulado' as number,
                            coalesce(r.name,'') as salary_rule,
                            a.amount as amount
                         from hr_contract_acumulados a
                         inner join hr_contract c on (c.id = a.contract_id)
                         inner join hr_employee e on (e.id = c.employee_id)
                         inner join hr_salary_rule r on (r.id = a.salary_rule_id)
                         where a.amount <> 0
                           and c.id = %(contrato)s
                           and r.cesantias = True                           
                           and a.date between %(fecha_prima)s::date and %(fecha_liquidacion)s::date                         
                         """, {
                    'contrato': contract_id.id,
                    'fecha_prima': payslip_detail.date_from,
                    'fecha_liquidacion': payslip_detail.date_to,
                })

            res = self.env.cr.fetchone()
            total = 0
            if res:
                grabar_datos(res)
                for result in res:
                    total += result[3]

            print('total ', total)
            payslip_detail.variable_total += total

            if payslip_detail.days_neto < 30:
                payslip_detail.variable_average = payslip_detail.variable_total
            else:
                payslip_detail.variable_average = (
                    (payslip_detail.variable_total) /
                    payslip_detail.days_neto) * 30

            resultado = payslip_detail.wage_average + payslip_detail.variable_average

        return resultado

    @api.model
    def calcular_cesantias(self,
                           date_liquidacion,
                           date_cesantia,
                           contract_id,
                           amount=0.0,
                           proyectado=False,
                           amount_salary=0.0,
                           payslip=None,
                           salary_code=None):
        print('############## calcular_cesantias')
        #Elimina calculos previos
        year_id = self.env['account.fiscalyear'].search([
            ('date_start', '<=', date_liquidacion),
            ('date_stop', '>=', date_liquidacion)
        ])

        unlink_ids = self.env['hr.contract.liquidacion'].search([
            ('contract_id', '=', self.id), ('sequence', '=', '1')
        ])
        if unlink_ids:
            for liq in unlink_ids:
                liq.unlink()

        #elimina el detalle previo
        salary_rule = self.env['hr.salary.rule'].search([('code', '=',
                                                          salary_code)])
        details_ids = self.env['hr.payslip.details'].search([
            ('slip_id', '=', payslip.id),
            ('salary_rule_id', '=', salary_rule.id)
        ])
        if details_ids:
            for detail in details_ids:
                detail.unlink()

        for cont in self:

            #------------  CESANTIA ------------------

            #valida fecha de liquidacion de contrato
            if not date_liquidacion:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de contrato"))

            #la fecha de liquidacion debe ser mayor que la de inicio de contrato
            day_start = cont.date_start
            day_end = date_liquidacion

            if (day_end - day_start).days <= 0:
                raise UserError(
                    _('Error!'),
                    _("La fecha de liquidación de contrato debe ser mayor a la fecha de inicio del mismo"
                      ))

            #calcula prima
            if not date_cesantia:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de cesantias"))

            #la fecha de liquidacion cesantia debe ser mayor que la de inicio de contrato
            day_to = date_cesantia
            if (day_to - day_start).days < 0:
                day_to = day_start
                #raise UserError(_('Error!'),_("La fecha de liquidación de prima debe ser mayor a la fecha de inicio del contrato"))

            dias = days_between(day_to, day_end)
            print('dias totales ', dias)

            payslip_detail = self.env['hr.payslip.details'].create({
                'slip_id':
                payslip.id,
                'salary_rule_id':
                salary_rule.id,
                'date_from':
                day_to,
                'date_to':
                day_end,
                'days_total':
                dias,
                'wage_total':
                amount_salary,
                'variable_total':
                amount,
            })

            # Busca las incapacidades en el mismo rango de fechas
            self.env.cr.execute(
                """select coalesce(sum(h.number_of_days),0) 
                           from hr_leave h
                           inner join hr_leave_type s on (s.id = h.holiday_status_id)
                           where h.employee_id = %(empleado)s
                             and h.request_date_from::date >= %(fecha_inicial)s::date
                             and h.request_date_to::date <= %(fecha_final)s::date
                             and s.unpaid = True
                             and h.state = 'validate'""", {
                    'empleado': contract_id.employee_id.id,
                    'fecha_inicial': date_cesantia,
                    'fecha_final': date_liquidacion,
                })
            ausencias = self.env.cr.fetchone()[0] or 0
            print('dias ausencias ', ausencias)
            payslip_detail.days_leave = ausencias
            dias = dias - ausencias
            payslip_detail.days_neto = dias
            print('Dias neto ', dias)

            promedio_salario_var = self.promedio_cesantias(
                contract_id, payslip_detail, proyectado)
            print('promedio_salario_var ', promedio_salario_var)
            grabar_linea2('Promedio salarial', promedio_salario_var)

            aux_transporte = 0.00
            if year_id:
                for ano in year_id:
                    #aux_transporte = (ano.sub_transporte /30) * dias
                    #Si gana menos de 2 salarios minimos legal vigente
                    if promedio_salario_var < ano.salario_minimo * 2:
                        aux_transporte = ano.sub_transporte

            print('Subsidio de transporte ', aux_transporte)
            grabar_linea2('Subsidio de transporte ', aux_transporte)
            payslip_detail.subsidio_transporte = aux_transporte

            base = round(aux_transporte + promedio_salario_var, 0)
            print('base ', base)
            grabar_linea2('Total base', base)
            payslip_detail.total_average = base
            grabar_linea2('Dias', dias)
            total_cesantia = round((base * dias) / 360, 0)
            print('total prima ', total_cesantia)
            grabar_linea2('Total cesantia', total_cesantia)
            payslip_detail.amount = total_cesantia

            print('Termina calcular cesantia')
            return total_cesantia

    @api.model
    def calcular_intereses(self,
                           date_liquidacion,
                           date_cesantia,
                           contract_id,
                           amount=0.0,
                           payslip=None,
                           salary_code=None):
        print('############## calcular_intereses')
        #Elimina calculos previos
        year_id = self.env['account.fiscalyear'].search([
            ('date_start', '<=', date_liquidacion),
            ('date_stop', '>=', date_liquidacion)
        ])

        unlink_ids = self.env['hr.contract.liquidacion'].search([
            ('contract_id', '=', self.id), ('sequence', '=', '1')
        ])
        if unlink_ids:
            for liq in unlink_ids:
                liq.unlink()

        #elimina el detalle previo
        salary_rule = self.env['hr.salary.rule'].search([('code', '=',
                                                          salary_code)])
        print('payslip.id ', payslip)
        print('salary_rule.id ', salary_rule)
        details_ids = self.env['hr.payslip.details'].search([
            ('slip_id', '=', payslip.id),
            ('salary_rule_id', '=', salary_rule.id)
        ])
        print('paso 1')
        if details_ids:
            for detail in details_ids:
                detail.unlink()

        for cont in self:

            #------------  INTERESES DE CESANTIAS ------------------

            #valida fecha de liquidacion de contrato
            if not date_liquidacion:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de contrato"))

            #la fecha de liquidacion debe ser mayor que la de inicio de contrato
            day_start = cont.date_start
            day_end = date_liquidacion

            if (day_end - day_start).days <= 0:
                raise UserError(
                    _('Error!'),
                    _("La fecha de liquidación de contrato debe ser mayor a la fecha de inicio del mismo"
                      ))

            #calcula prima
            if not date_cesantia:
                raise UserError(
                    _('Error!'),
                    _("Debe ingresar fecha de liquidación de cesantias"))

            #la fecha de liquidacion cesantia debe ser mayor que la de inicio de contrato
            day_to = date_cesantia
            if (day_to - day_start).days < 0:
                day_to = day_start
                #raise UserError(_('Error!'),_("La fecha de liquidación de prima debe ser mayor a la fecha de inicio del contrato"))

            dias = days_between(day_to, day_end)
            print('dias totales ', dias)

            payslip_detail = self.env['hr.payslip.details'].create({
                'slip_id':
                payslip.id,
                'salary_rule_id':
                salary_rule.id,
                'date_from':
                day_to,
                'date_to':
                day_end,
                'days_total':
                dias,
                'wage_total':
                0,
                'variable_total':
                amount,
            })

            # Busca las incapacidades en el mismo rango de fechas
            self.env.cr.execute(
                """select coalesce(sum(h.number_of_days),0) 
                           from hr_leave h
                           inner join hr_leave_type s on (s.id = h.holiday_status_id)
                           where h.employee_id = %(empleado)s
                             and h.request_date_from::date >= %(fecha_inicial)s::date
                             and h.request_date_to::date <= %(fecha_final)s::date
                             and s.unpaid = True
                             and h.state = 'validate'""", {
                    'empleado': contract_id.employee_id.id,
                    'fecha_inicial': date_cesantia,
                    'fecha_final': date_liquidacion,
                })
            ausencias = self.env.cr.fetchone()[0] or 0
            print('dias ausencias ', ausencias)
            payslip_detail.days_leave = ausencias
            dias = dias - ausencias
            payslip_detail.days_neto = dias
            print('Dias neto ', dias)

            payslip_detail.subsidio_transporte = 0

            base = amount
            print('base ', base)
            grabar_linea2('Total base', base)
            payslip_detail.total_average = base
            grabar_linea2('Dias', dias)
            total_intereses = round((base * dias * 0.12) / 360, 0)
            print('total intereses ', total_intereses)
            grabar_linea2('Total intereses', total_intereses)
            payslip_detail.amount = total_intereses

            print('Termina calcular intereses')
            return total_intereses

    @api.model
    def create_report_sheet(self, payslip):
        print('** create_report_sheet')
        slip = self.env['hr.payslip'].browse([payslip.id])
        filename = self.create_report_xls(payslip)

        datos_global = {
            'Fecha': col_fecha,
            'Nómina No.': col_nomina,
            'Regla salarial': col_regla,
            'Valor': col_valor
        }
        dframe = pd.DataFrame(datos_global)
        ew = pd.ExcelWriter(filename, engine='xlsxwriter')
        dframe.to_excel(ew,
                        index=False,
                        sheet_name='Detalle',
                        encoding='utf8',
                        startrow=2)
        workbook = ew.book
        float_fmt = workbook.add_format({
            'num_format': '#,##0.00',
            'bold': False,
            'align': 'right',
            'border': 0
        })
        string_fmt = workbook.add_format({
            'bold': False,
            'align': 'left',
            'border': 0
        })

        worksheet = ew.sheets['Detalle']
        worksheet.set_zoom(90)
        worksheet.write(0, 0, 'Empleado:', string_fmt)
        worksheet.write(0, 1, payslip.contract_id.employee_id.name, string_fmt)
        ew.save()
        ew.close()
        self.create_attachment(filename, payslip)

        print('== termina create_report_sheet ==')

    @api.model
    def create_report_xls(self, payslip):
        print('*** create_report_xls')
        slip = self.env['hr.payslip'].browse([payslip.id])
        home_report = self.env["ir.config_parameter"].get_param(
            "home.odoo.report")
        if not home_report:
            raise UserError(
                'Falta configurar el parámetro del sistema con clave home.odoo.report'
            )

        if not payslip.number:
            number = self.env['ir.sequence'].next_by_code('salary.slip')
            archivo = number.replace('/', '-') + '.xlsx'
        else:
            archivo = payslip.number.replace('/', '-') + '.xlsx'

        filename = home_report + archivo

        return filename

    @api.model
    def create_attachment(self, filename, payslip):
        print('** create_attachment')
        #Adjunta el documento
        data = open(filename, "rb").read()
        if not payslip.number:
            number = self.env['ir.sequence'].next_by_code('salary.slip')
            filename = number.replace('/', '-') + '.xlsx'
        else:
            number = False
            filename = payslip.number.replace('/', '-') + '.xlsx'

        data_attach = {
            'name': filename,
            'datas': base64.encodestring(data),
            'datas_fname': filename,
            'description': 'Nómina ' + (payslip.number or number),
            'res_model': 'hr.payslip',
            'res_id': payslip.id,
        }
        #si existen adjuntos lo borra primero
        for att in self.env['ir.attachment'].sudo().search([
            ('datas_fname', '=', filename), ('res_id', '=', payslip.id)
        ]):
            att.unlink()

        self.env['ir.attachment'].sudo().create(data_attach)
