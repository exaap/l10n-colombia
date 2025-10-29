# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models, _


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    invoice_type_code = fields.Selection(
        selection_add=[("02", _("E-invoice of sale - exportation"))]
    )
