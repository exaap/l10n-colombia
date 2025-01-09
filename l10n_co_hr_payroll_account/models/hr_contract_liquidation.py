# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import fields, models


class HrContractliquidation(models.Model):
    _name = 'hr.contract.liquidation'
    _description = 'Contract liquidation detail'
    _order = 'contract_id, sequence'

    sequence = fields.Integer(string='Sequence', required=True)
    name = fields.Char(string='Concept', size=100, required=True)
    base = fields.Float(string='Base', required=True, default=0)
    since = fields.Date(string='Since', required=False)
    until = fields.Date(string='Until', required=False)
    days = fields.Float(string='Days', required=True, default=1)
    amount = fields.Float(string='Value', required=True, default=0)
    contract_id = fields.Many2one(comodel_name='hr.contract',
                                  string="liquidation",
                                  required=True,
                                  ondelete='cascade',
                                  index=True)
