# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models, _


class AccountPaymentMeanCode(models.Model):
    _name = "account.payment.mean.code"
    _description = "Payment Means"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True)

    _sql_constraints = [
        (
            "code_and_name_unique",
            "unique(code, name)",
            _("The combination of code and name must be unique"),
        )
    ]
