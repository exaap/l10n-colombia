# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, fields, api


class AccountInvoiceDebitnote(models.TransientModel):
    _inherit = "account.invoice.debitnote"

    reason_id = fields.Many2one(
        comodel_name="account.invoice.refund.reason",
        string="Correction Concept",
        required=True,
        domain="[('type', '=', 'debit')]",
    )

    @api.onchange("reason_id")
    def _onchange_reason_id(self):
        if self.reason_id:
            self.description = self.reason_id.name

    @api.multi
    def compute_debitnote(self):
        res = super().compute_debitnote()
        inv_obj = self.env["account.invoice"]

        if isinstance(res["domain"], list):
            invoice_domain = []

            for domain in res["domain"]:
                if "type" not in domain:
                    invoice_domain.append(domain)

            invoice_id = inv_obj.search(invoice_domain)
            res["domain"] = invoice_domain

            if invoice_id:
                invoice_id.reason_id = self.reason_id.id
                debit_invoice_id = invoice_id.debit_invoice_id
                invoice_id.partner_shipping_id = debit_invoice_id.partner_shipping_id.id

        return res
