# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models, _

DIAN_TYPES = [
    ("e-invoicing", _("E-Invoicing")),
    ("e-credit_note", _("E-Credit Note")),
    ("e-debit_note", _("E-Debit Note")),
    ("e-support_document", _("E-Support Document")),
    ("e-support_document_credit_note", _("E-Support Document Credit Note")),
    ("contingency_checkbook_e-invoicing", _("Contingency Checkbook E-Invoicing")),
]


class IrSequence(models.Model):
    _inherit = "ir.sequence"

    dian_type = fields.Selection(selection_add=DIAN_TYPES)
