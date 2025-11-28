# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import re
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

ID_TYPE_CODES = ["11", "12", "13", "21", "22", "31", "41", "42", "47", "48", "50", "91"]
TAX_DETAILS = {"01": "IVA", "04": "INC", "ZA": "IVA e INC", "ZZ": "No aplica"}


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_einvoicing_agent = fields.Selection(
        selection=[
            ("yes", "Yes"),
            ("no_but", "No, but has email"),
            ("no", "No"),
            ("unknown", "Unknown"),
        ],
        string="Is an E-Invoicing Agent?",
        default=False,
    )
    einvoicing_email = fields.Char(string="E-Invoicing Email")
    view_einvoicing_email_field = fields.Boolean(
        string="View 'E-Invoicing Email' Fields",
        compute="_get_view_einvoicing_email_field",
        store=False,
    )
    edit_is_einvoicing_agent_field = fields.Boolean(
        string="Edit 'Is an E-Invoicing Agent?' Field",
        compute="_get_edit_is_einvoicing_agent_field",
        store=False,
    )

    @api.onchange("company_type")
    def onchange_company_type(self):
        super(ResPartner, self).onchange_company_type()

        if self.company_type == "company":
            self.is_einvoicing_agent = "yes"

        self.property_account_position_id = False

    @api.multi
    def _get_view_einvoicing_email_field(self):
        view_einvoicing_email_field = False

        if self.env.user.has_group(
            "l10n_co_account_edi.group_view_einvoicing_email_fields"
        ):
            view_einvoicing_email_field = True

        for partner in self:
            partner.view_einvoicing_email_field = view_einvoicing_email_field

    @api.multi
    def _get_edit_is_einvoicing_agent_field(self):
        edit_is_einvoicing_agent_field = False

        if self.env.user.has_group(
            "l10n_co_account_edi.group_edit_is_einvoicing_agent_field"
        ):
            edit_is_einvoicing_agent_field = True

        for partner in self:
            partner.edit_is_einvoicing_agent_field = edit_is_einvoicing_agent_field

    @api.constrains("einvoicing_email")
    @api.onchange("einvoicing_email")
    def validate_mail(self):
        if self.einvoicing_email:
            match = re.match(
                r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)",
                self.einvoicing_email,
            )

            if match is None:
                raise ValidationError(
                    _(
                        "The field 'E-Invoicing Email' is not correctly filled.\n\n"
                        "Please add @ and dot (.)"
                    )
                )

    def _get_accounting_partner_party_values(self):
        msg1 = _("'%s' does not have a city established.")
        msg2 = _("'%s' does not have a state established.")
        msg3 = _("'%s' does not have a country established.")
        msg4 = _("'%s' does not have a verification digit established.")
        msg5 = _("'%s' does not have a DIAN document type established.")
        msg6 = _(
            "The document type of '%s' does not seem to correspond with the "
            "person type."
        )
        msg7 = _("'%s' does not have a identification document established.")
        msg8 = _("E-Invoicing Agent: '%s' does not have a E-Invoicing Email.")
        msg9 = _("'%s' does not have a fiscal position established.")
        msg10 = _("'%s' does not have a fiscal position correctly configured.")
        partner_name = self.name
        fiscal_postion_id = self.property_account_position_id
        identification_type_code = self.l10n_co_identification_type_code
        identification_document = self.l10n_co_identification_document
        telephone = False

        if self.country_id:
            if self.country_id.code == "CO":
                if not self.zip_id:
                    raise UserError(msg1 % partner_name)
                elif not self.state_id:
                    raise UserError(msg2 % partner_name)
        else:
            raise UserError(msg3 % partner_name)

        if not identification_type_code:
            raise UserError(msg5 % partner_name)

        if identification_type_code == "31" and not self.l10n_co_verification_digit:
            raise UserError(msg4 % partner_name)

        # Punto 6.2.1. Documento de identificación (Tipo de Identificador Fiscal):
        # cbc:CompanyID.@schemeName; sts:ProviderID.@schemeName del anexo técnico version 1.7
        if identification_type_code not in ID_TYPE_CODES:
            if self.company_type == "company":
                raise UserError(msg5 % partner_name)
            else:
                partner_name = "consumidor final"
                identification_type_code = "13"
                identification_document = "222222222222"

        if (
            self.company_type == "company"
            and identification_type_code not in ("31", "50")
        ) or (
            self.company_type == "person" and identification_type_code in ("31", "50")
        ):
            raise UserError(msg6 % partner_name)

        if not identification_document:
            raise UserError(msg7 % partner_name)

        if (
            self.is_einvoicing_agent in ("yes", "not_but")
            or not self.is_einvoicing_agent
        ) and not self.einvoicing_email:
            raise UserError(msg8 % partner_name)

        if not fiscal_postion_id:
            raise UserError(msg9 % partner_name)

        fiscal_responsibility_ids = fiscal_postion_id.fiscal_responsibility_ids

        if not fiscal_responsibility_ids or not fiscal_postion_id.tax_detail:
            raise UserError(msg10 % partner_name)

        if identification_document == "222222222222":
            tax_level_codes = "R-99-PN"
            tax_scheme_code = "ZZ"
        else:
            fiscal_responsibility_codes = fiscal_responsibility_ids.mapped("code")
            tax_level_codes = ";".join(fiscal_responsibility_codes)
            tax_scheme_code = fiscal_postion_id.tax_detail

        if self.phone and self.mobile:
            telephone = self.phone + " / " + self.mobile
        elif self.phone:
            telephone = self.phone
        elif self.mobile:
            telephone = self.mobile

        return {
            "AdditionalAccountID": "1" if self.company_type == "company" else "2",
            "PartyName": self.commercial_name,
            "RegistrationName": partner_name,
            "AddressID": self.zip_id.city_id.code or "",
            "AddressCityName": (self.zip_id.city_id.name or (self.city or "")).title(),
            "AddressPostalZone": self.zip_id.name if self.zip_id else False,
            "AddressCountrySubentity": self.state_id.name or "",
            "AddressCountrySubentityCode": self.state_id.code or "",
            "AddressLine": self.street or "",
            "CompanyIDschemeID": self.l10n_co_verification_digit,
            "CompanyIDschemeName": identification_type_code,
            "CompanyID": identification_document,
            "TaxLevelCode": tax_level_codes,
            "TaxSchemeID": tax_scheme_code,
            "TaxSchemeName": TAX_DETAILS[tax_scheme_code],
            "CorporateRegistrationSchemeName": self.coc_registration_number,
            "CountryIdentificationCode": self.country_id.code,
            "CountryName": self.country_id.name_dian,
            "Telephone": telephone,
            "Telefax": False,
            "ElectronicMail": self.einvoicing_email,
        }

    def _get_delivery_values(self):
        msg1 = _("'%s' does not have a city established.")
        msg2 = _("'%s' does not have a state established.")
        msg3 = _("'%s' does not have a country established.")

        if self.country_id:
            if self.country_id.code == "CO":
                if not self.zip_id:
                    raise UserError(msg1 % self.name)
                elif not self.state_id:
                    raise UserError(msg2 % self.name)
        else:
            raise UserError(msg3 % self.name)

        return {
            "AddressID": self.zip_id.city_id.code or "",
            "AddressCityName": self.zip_id.city_id.name or (self.city or ""),
            "AddressPostalZone": self.zip_id.name if self.zip_id else False,
            "AddressCountrySubentity": self.state_id.name or "",
            "AddressCountrySubentityCode": self.state_id.code or "",
            "AddressLine": self.street or "",
            "CountryIdentificationCode": self.country_id.code,
            "CountryName": self.country_id.name_dian,
        }

    def _get_tax_representative_party_values(self):
        msg1 = _("'%s' does not have a verification digit established.")
        msg2 = _("'%s' does not have a document type established.")
        msg3 = _("'%s' does not have a identification document established.")

        if self.l10n_co_identification_type_code:
            if (
                self.l10n_co_identification_type_code == "31"
                and not self.l10n_co_verification_digit
            ):
                raise UserError(msg1 % self.name)
        else:
            raise UserError(msg2 % self.name)

        if not self.l10n_co_identification_document:
            raise UserError(msg3 % self.name)

        return {
            "IDschemeID": self.l10n_co_verification_digit,
            "IDschemeName": self.l10n_co_identification_type_code,
            "ID": self.l10n_co_identification_document,
        }
