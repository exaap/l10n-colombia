# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import re
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EInvoiceNotificationGroup(models.Model):
    _name = "einvoice.notification.group"
    _description = "Notification Group"

    name = fields.Char(string="Name")
    email = fields.Char(string="Email")
    company_id = fields.Many2one(comodel_name="res.company", string="Company")

    @api.model
    def create(self, vals):
        rec = super(EInvoiceNotificationGroup, self).create(vals)
        # Check email address is valid or not
        if rec.email:
            if (
                re.match(
                    "^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$",
                    rec.email,
                )
                is None
            ):
                raise ValidationError("Please enter a valid email address")

        return rec

    @api.multi
    def write(self, values):
        result = super(EInvoiceNotificationGroup, self).write(values)
        # Check email address is valid or not
        if values.get("email"):
            if (
                re.match(
                    "^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$",
                    values.get("email"),
                )
                is None
            ):
                raise ValidationError("Please enter a valid email address")

        return result
