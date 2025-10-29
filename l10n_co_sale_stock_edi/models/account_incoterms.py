# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models


class AccountIncoterms(models.Model):
    _inherit = "account.incoterms"

    is_einvoicing = fields.Boolean(string="Does it Apply for E-Invoicing?")

    def name_get(self):
        res = []

        for record in self:
            if record.is_einvoicing:
                name = "[DIAN][%s] %s" % (record.code or "", record.name or "")
            else:
                name = "[%s] %s" % (record.code or "", record.name or "")

            res.append((record.id, name))

        return res
