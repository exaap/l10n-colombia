# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, _
from odoo.exceptions import UserError


class AccountInvoiceDianDocument(models.Model):
    _inherit = "account.invoice.dian.document"

    def _get_xml_values(self, ClTec):
        msg1 = _(
            "The 'e-invoice of sale - exportation' must have an incoterm DIAN established."
        )
        msg2 = _("'%s', must have a brand established.")
        msg3 = _("'%s', must have a ref established.")
        res = super(AccountInvoiceDianDocument, self)._get_xml_values(ClTec)

        if self.invoice_id.invoice_type_code == "02":
            if (
                not self.invoice_id.incoterm_id
                and not self.invoice_id.incoterm_id.is_einvoicing
            ):
                raise UserError(msg1)
            else:
                res["DeliveryTerms"] = {
                    "LossRiskResponsibilityCode": self.invoice_id.incoterm_id.code,
                    "LossRisk": self.invoice_id.incoterm_id.name,
                }

            for invoice_line in self.invoice_id.invoice_line_ids:
                if not invoice_line.product_id.product_brand_id:
                    raise UserError(msg2 % invoice_line.name)

                if not invoice_line.product_id:
                    raise UserError(msg3 % invoice_line.name)

        return res
