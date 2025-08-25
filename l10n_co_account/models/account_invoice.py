# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models, api


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    def _compute_payment_mean(self):
        payment_mean = "1"

        if self.date_invoice and self.date_due and self.date_invoice != self.date_due:
            payment_mean = "2"

        self.payment_mean = payment_mean

    payment_mean = fields.Selection(
        selection=[("1", "Cash"), ("2", "Credit")],
        string="Payment Method",
        compute=_compute_payment_mean,
        store=False,
    )
    payment_mean_code_id = fields.Many2one(
        comodel_name="account.payment.mean.code", string="Payment Mean", copy=False
    )
    reason_id = fields.Many2one(
        comodel_name="account.invoice.refund.reason",
        string="Correction Concept",
        domain="[('type', 'in', {'out_invoice': ['debit'], 'out_refund': ['credit']}.get(type, []))]",
    )

    @api.onchange("payment_term_id")
    def _onchange_payment_term_id(self):
        if self.payment_term_id and self.payment_term_id != self.env.ref(
            "account.account_payment_term_immediate"
        ):
            self.payment_mean_code_id = self.env.ref(
                "l10n_co_account.account_payment_mean_code_001"
            ).id

    @api.model
    def create(self, vals):
        res = super(AccountInvoice, self).create(vals)

        for invoice in res:
            invoice._onchange_payment_term()

        return res
