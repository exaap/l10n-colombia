# Copyright 2026 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, fields


class L10nCoAccountExogenaReportLine(models.Model):
    _name = "l10n_co.account.exogena.report.line"
    _description = "Exogena Report Line"

    exogena_report_id = fields.Many2one(
        comodel_name="l10n_co.account.exogena.report", required=True
    )
    concept = fields.Char(required=True)
    account_id = fields.Many2one(comodel_name="account.account", required=True)
    column = fields.Char(required=True)
