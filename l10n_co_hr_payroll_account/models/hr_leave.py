# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import time
import math
import datetime
from datetime import date, timedelta
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class HrHolidays(models.Model):
    _description = "Leave"
    _inherit = "hr.leave"

    def _compute_days_real(self, cr, uid, ids, name, args, context=None):
        check_pool = self.pool.get("account.check")
        rs_data = {}

        employee_obj = self.pool.get("hr.employee")
        holidays_obj = self.pool.get("hr.holidays.public")
        DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

        for line in self.browse(cr, uid, ids, context=context):
            diff_day = 0.0
            f_desde = datetime.strptime(line.date_from, DATETIME_FORMAT).date()
            f_hasta = datetime.strptime(line.date_to, DATETIME_FORMAT).date()

            # Determina si el empleado trabaja el sabado y cuando sabado hay en el rango de fechas
            for emp in employee_obj.browse(
                cr, uid, [line.employee_id.id], context=None
            ):
                sabado = emp.sabado

            diff_day = 0
            delta = timedelta(days=1)

            while f_desde <= f_hasta:
                if (not sabado and f_desde.strftime("%A").upper() == "SATURDAY") or (
                    f_desde.strftime("%A").upper() == "SUNDAY"
                ):
                    print("Es sabado no habil o domingo")
                else:
                    if holidays_obj.is_public_holiday(cr, uid, f_desde, context=None):
                        print("Es festivo")
                    else:
                        diff_day = diff_day + 1

                f_desde += delta

            rs_data[line.id] = diff_day

        return rs_data

    def _get_number_of_days_new(self, date_from, date_to, employee_id):
        """Returns a float equals to the timedelta between two dates given as string."""

        DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

        from_dt = datetime.datetime.strptime(date_from, DATETIME_FORMAT).date()
        to_dt = datetime.datetime.strptime(date_to, DATETIME_FORMAT).date()

        dias = 0
        delta = datetime.timedelta(days=1)
        while from_dt <= to_dt:
            dias = dias + 1
            if from_dt.month == 2:
                if from_dt.day == 28:
                    dias = dias + 2
                if from_dt.day == 29:
                    dias = dias + 1

            if (from_dt.month in (1, 3, 5, 7, 8, 10, 12)) and (from_dt.day == 31):
                dias = dias - 1

            from_dt += delta

        return dias
