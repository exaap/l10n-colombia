# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, fields


class AccountInvoiceDianDocumentLine(models.Model):
    _name = "account.invoice.dian.document.line"
    _order = "create_date desc"
    _description = "DIAN Document Line"

    dian_document_id = fields.Many2one(
        comodel_name="account.invoice.dian.document", string="DIAN Document"
    )
    send_async_status_code = fields.Char(string="Status Code")
    send_async_reason = fields.Char(string="Reason")
    send_async_response = fields.Text(string="Response")
