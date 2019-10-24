# -*- coding: utf-8 -*-
# Copyright 2019 Juan Camilo Zuluaga Serna <Github@camilozuluaga>
# Copyright 2019 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
	"name": "Responsabilidades Fiscales para la localizacion Colombiana",
	"version": "10.0.1.0.0",
	"website": "https://github.com/odooloco/l10n-colombia",
	"author": "Juan Camilo Zuluaga Serna Github@camilozuluaga, "
              "Joan Marín Github@JoanMarin",
	"category": "Localization",
	"summary": "Este módulo tiene las responsabilidades fiscales identificados "
			   "por la DIAN para la localizacion Colombiana",
	"depends": [
		"account",
		"l10n_co_partner_vat"
	],
	"data": [
		"security/ir.model.access.csv",
		"data/res_partner_tax_level_code_data.xml",
		"views/res_partner_tax_level_code_views.xml",
		"views/res_partner_views.xml",
	],
	"installable": True,
}