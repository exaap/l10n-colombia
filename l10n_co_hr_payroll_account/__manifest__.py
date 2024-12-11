# Copyright 2021 Alejandro Olano <Github@alejo-code>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

{
    "name": "Nomina Localizacion Colombiana",
    "version": "12.0.1.0.0",
    "author": "EXA Auto Parts Github@exaap, Alejandro Olano Github@alejo-code",
    "category": "Generic Modules/Human Resources",
    "depends": [
        "hr_payroll_account",
        "l10n_co_account_fiscal_year",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_contract_risk.xml",
        "data/hr_contribution_register.xml",
        "views/hr_payslip_view.xml",
        "views/hr_payslip_run_view.xml",
        "views/hr_employee_view.xml",
        "views/hr_department_view.xml",
        "views/hr_salary_rule_view.xml",
        "views/hr_salary_rule_category_view.xml",
        "views/hr_contract_view.xml",
        "views/hr_contract_setting_view.xml",
        "views/hr_contract_accumulated_view.xml",
        "views/hr_contract_deduction_view.xml",
        "views/hr_contract_risk_view.xml",
        "views/hr_payroll_news_view.xml",
        "views/res_config_settings_view.xml",
    ],
}
