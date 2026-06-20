# Copyright 2026 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

{
    "name": "Colombian Localization Account Exogena",
    "version": "12.0.1.0.0",
    "category": "Localization",
    "author": "EXA Auto Parts Github@exaap, "
    "Joan Marín Github@JoanMarin, "
    "Odoo Community Association (OCA)",
    "maintainers": ["joanmarin"],
    "website": "https://github.com/OCA/l10n-colombia",
    "depends": [
        "l10n_co_account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/l10n_co_account_exogena_report.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
