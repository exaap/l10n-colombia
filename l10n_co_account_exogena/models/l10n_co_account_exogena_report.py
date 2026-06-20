# Copyright 2026 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, api, fields, _


class L10nCoAccountExogenaReport(models.Model):
    _name = "l10n_co.account.exogena.report"
    _description = "Exogena Report"

    name = fields.Char(required=True)
    year = fields.Char()
    exogena_report_line_ids = fields.One2many(
        comodel_name="l10n_co.account.exogena.report.line",
        inverse_name="exogena_report_id",
        string="Exogena Report Lines",
    )
