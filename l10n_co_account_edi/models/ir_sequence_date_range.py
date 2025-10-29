# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models


class IrSequenceDateRange(models.Model):
    _inherit = "ir.sequence.date_range"

    dian_type = fields.Selection(
        string="DIAN Type", related="sequence_id.dian_type", store=False
    )
    technical_key = fields.Char(string="Technical Key")
