# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import phonenumbers
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    company_type = fields.Selection(
        selection=[("person", "Natural Person"), ("company", "Juridical Person")]
    )
    l10n_latam_identification_type_id = fields.Many2one(default=False)
    l10n_co_identification_type_code = fields.Char(
        related="l10n_latam_identification_type_id.code_dian", store=False
    )
    l10n_co_identification_document = fields.Char(
        string="Identification Document", placeholder="Identification Document"
    )
    l10n_co_verification_digit = fields.Char(
        string="Verification Digit", placeholder="Verification Digit", size=1
    )
    industry_id = fields.Many2one(domain="[('type', '!=', 'view')]")
    secondary_industry_ids = fields.Many2many(
        domain="[('id', '!=', industry_id), ('type', '!=', 'view')]"
    )

    @api.onchange("country_id")
    def _onchange_country(self):
        if self.country_id.code == "CO":
            self.l10n_latam_identification_type_id = False
        else:
            super(ResPartner, self)._onchange_country()

    @api.onchange(
        "country_id",
        "l10n_latam_identification_type_id",
        "l10n_co_identification_document",
        "l10n_co_verification_digit",
    )
    def _onchange_vat(self):
        if self.country_id and self.l10n_co_identification_document:
            if (
                self.l10n_co_verification_digit
                and self.l10n_co_identification_type_code == "31"
            ):
                self.vat = (
                    self.country_id.code
                    + self.l10n_co_identification_document
                    + self.l10n_co_verification_digit
                )
            elif self.l10n_co_identification_type_code == "43":
                self.l10n_co_verification_digit = False
                self.vat = "CO" + self.l10n_co_identification_document
            else:
                self.l10n_co_verification_digit = False
                self.vat = self.country_id.code + self.l10n_co_identification_document
        elif not self.l10n_co_identification_document and self.vat:
            self.vat = False

    def _compute_verification_digit(self):
        if not self.l10n_co_identification_document:
            return False

        prime = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
        identification_document = self.l10n_co_identification_document.strip()
        verification_digit = 0

        for i, character in enumerate(identification_document[::-1]):
            try:
                digit = int(character)
            except:
                return False

            verification_digit += digit * prime[i]

        verification_digit %= 11
        verification_digit = verification_digit if verification_digit >= 0 else 0

        return (
            (11 - verification_digit) if verification_digit >= 2 else verification_digit
        )

    @api.model
    def name_search(self, name, args=None, operator="ilike", limit=100):
        args = args or []

        if name:
            args = [
                "|",
                "|",
                ("display_name", operator, name),
                ("vat", operator, name),
                ("email", operator, name),
            ] + args

        return self.search(args, limit=limit).name_get()

    def l10n_co_format_number(self):
        msg1 = _("The area code for number %s is incorrect. Area code: %s")
        msg2 = _("The number %s is invalid. E.g.: 3001234567 or 6041234567")

        for partner_id in self:
            if partner_id.country_id.code != "CO":
                continue

            for field in ["phone", "mobile"]:
                number = getattr(partner_id, field)

                if not number:
                    continue

                if field == "phone":
                    phone_code = "60" + partner_id.state_id.phone_code

                    if len(number) == 7:
                        number = phone_code + number
                    elif phone_code != number[:3]:
                        raise ValidationError(msg1 % (number, phone_code))

                try:
                    parse_number = phonenumbers.parse(number, "CO")

                    if not phonenumbers.is_valid_number(parse_number):
                        raise ValidationError(msg2 % number)

                    number = phonenumbers.format_number(
                        parse_number, phonenumbers.PhoneNumberFormat.NATIONAL
                    )
                    number = number.replace(" ", "").replace("-", "")
                    number = number.replace("(", "").replace(")", "")
                except phonenumbers.NumberParseException as e:
                    raise ValidationError(_("ERROR: %s") % e)

                partner_id.with_context(no_edit=True).write({field: number})

    def write(self, vals):
        res = super(ResPartner, self).write(vals)

        if not self._context.get("no_edit") and (
            vals.get("phone") or vals.get("mobile")
        ):
            self.l10n_co_format_number()

        return res
