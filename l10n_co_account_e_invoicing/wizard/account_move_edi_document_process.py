# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveEdiDocumentProcess(models.TransientModel):
    _name = "account.move.edi.document.process"
    _description = "Account Move EDI Document Process"

    action = fields.Selection(
        selection=[
            ("e-invoice_receipt", "E-invoice Receipt"),
            ("as_receipt", "Assets and/or Services Receipt"),
            ("express_acceptance", "Express Acceptance"),
        ],
        string="Action",
    )

    @api.multi
    def action_edi_document_process(self):
        record_ids = self.env.context.get("active_ids", False)
        invoice_obj = self.env["account.invoice"]
        invoice_action = self.action
        invoice_ids = invoice_obj.browse(record_ids)

        for invoice_id in invoice_ids:
            if not invoice_id.supplier_uuid:
                continue

            if (
                invoice_action == "e-invoice_receipt"
                and not invoice_id.dian_document_state
            ):
                invoice_id.action_ApplicationResponse_030()
            elif (
                invoice_action == "as_receipt"
                and invoice_id.dian_document_state == "e-invoice_receipt"
            ):
                invoice_id.action_ApplicationResponse_032()
            elif (
                invoice_action == "express_acceptance"
                and invoice_id.dian_document_state == "as_receipt"
            ):
                invoice_id.action_ApplicationResponse_033()

        return {
            "type": "ir.actions.act_window",
            "domain": "[('id','in', [" + ",".join(map(str, record_ids)) + "])]",
            "name": _("Invoices"),
            "view_type": "tree",
            "view_mode": "tree",
            "res_model": "account.invoice",
            "view_id": self.env.ref("account.invoice_supplier_tree").id,
            "context": False,
        }
