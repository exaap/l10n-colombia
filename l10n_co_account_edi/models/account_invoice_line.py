# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from odoo import models, fields, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError


class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    cost_price = fields.Float(
        string="Cost Price", digits=dp.get_precision("Product Price"), default=0
    )
    reference_price = fields.Float(
        string="Reference Price", digits=dp.get_precision("Product Price"), default=0
    )

    def _get_information_content_provider_party_values(self):
        return {"IDschemeID": False, "IDschemeName": False, "ID": False}

    def _get_line_taxes_total(self, tax_id, line_taxes_total):
        tax_code = tax_id.tax_group_id.tax_group_type_id.code
        tax_name = tax_id.tax_group_id.tax_group_type_id.name
        tax_percent = "{:.2f}".format(tax_id.amount)
        tax_base = self.price_subtotal
        tax_total = tax_base * tax_id.amount / 100

        if tax_code not in line_taxes_total:
            line_taxes_total[tax_code] = {}
            line_taxes_total[tax_code]["total"] = 0
            line_taxes_total[tax_code]["name"] = tax_name
            line_taxes_total[tax_code]["taxes"] = {}

        if tax_percent not in line_taxes_total[tax_code]["taxes"]:
            line_taxes_total[tax_code]["taxes"][tax_percent] = {}
            line_taxes_total[tax_code]["taxes"][tax_percent]["base"] = 0
            line_taxes_total[tax_code]["taxes"][tax_percent]["amount"] = 0

        line_taxes_total[tax_code]["total"] += tax_total
        line_taxes_total[tax_code]["taxes"][tax_percent]["base"] += tax_base
        line_taxes_total[tax_code]["taxes"][tax_percent]["amount"] += tax_total

        return line_taxes_total

    def _get_line_taxes(self, invoice_line):
        msg1 = _(
            "Your tax: '%s', has no e-invoicing tax group type, contact with your "
            "administrator."
        )
        msg2 = _(
            "Your withholding tax: '%s', has amount equal to zero (0), the "
            "withholding taxes must have amount different to zero (0), contact "
            "with your administrator."
        )
        msg3 = _(
            "Your tax: '%s', has negative amount or an amount equal to zero (0), "
            "the taxes must have an amount greater than zero (0), contact with "
            "your administrator."
        )
        tax_ids = self.env["account.tax"]

        for tax_id in self.invoice_line_tax_ids:
            if tax_id.amount_type == "group":
                tax_ids |= tax_id.children_tax_ids
            else:
                tax_ids |= tax_id

        for tax_id in tax_ids:
            if not tax_id.tax_group_id.is_einvoicing:
                continue

            if not tax_id.tax_group_id.tax_group_type_id:
                raise UserError(msg1 % tax_id.name)

            tax_type = tax_id.tax_group_id.tax_group_type_id.type

            if tax_type == "withholding_tax" and tax_id.amount == 0:
                raise UserError(msg2 % tax_id.name)

            if tax_type == "tax" and tax_id.amount <= 0:
                raise UserError(msg3 % tax_id.name)

            if tax_type == "withholding_tax" and tax_id.amount > 0:
                invoice_line["WithholdingTaxesTotal"] = self._get_line_taxes_total(
                    tax_id, invoice_line["WithholdingTaxesTotal"]
                )
            elif tax_type == "withholding_tax" and tax_id.amount < 0:
                # TODO 3.0 Las retenciones se recomienda no enviarlas a la DIAN.
                # Solo la parte positiva que indicaria una autoretencion, Si la DIAN
                # pide que se envie la parte negativa, seria quitar o comentar este if
                pass
            else:
                invoice_line["TaxesTotal"] = self._get_line_taxes_total(
                    tax_id, invoice_line["TaxesTotal"]
                )

        return invoice_line

    def _set_line_taxes_total(self, line_taxes_total, base):
        if "01" not in line_taxes_total:
            line_taxes_total["01"] = {}
            line_taxes_total["01"]["total"] = 0
            line_taxes_total["01"]["name"] = "IVA"
            line_taxes_total["01"]["taxes"] = {}
            line_taxes_total["01"]["taxes"]["0.00"] = {}
            line_taxes_total["01"]["taxes"]["0.00"]["base"] = base
            line_taxes_total["01"]["taxes"]["0.00"]["amount"] = 0

        if "04" not in line_taxes_total:
            line_taxes_total["04"] = {}
            line_taxes_total["04"]["total"] = 0
            line_taxes_total["04"]["name"] = "ICA"
            line_taxes_total["04"]["taxes"] = {}
            line_taxes_total["04"]["taxes"]["0.00"] = {}
            line_taxes_total["04"]["taxes"]["0.00"]["base"] = base
            line_taxes_total["04"]["taxes"]["0.00"]["amount"] = 0

        if "03" not in line_taxes_total:
            line_taxes_total["03"] = {}
            line_taxes_total["03"]["total"] = 0
            line_taxes_total["03"]["name"] = "INC"
            line_taxes_total["03"]["taxes"] = {}
            line_taxes_total["03"]["taxes"]["0.00"] = {}
            line_taxes_total["03"]["taxes"]["0.00"]["base"] = base
            line_taxes_total["03"]["taxes"]["0.00"]["amount"] = 0

        return line_taxes_total

    def _get_invoice_lines(self, invoice_type_code):
        msg1 = _("The invoice line %s has no reference")
        msg2 = _(
            "Your product: '%s', has no reference price, contact with your "
            "administrator."
        )
        invoice_lines = {}
        item = 1
        line_ids = self.filtered(lambda x: not x.product_set_sale_id)

        for line_id in line_ids:
            disc_amount = 0
            total_wo_disc = 0
            brand_name = False
            model_name = False

            if line_id.price_unit != 0 and line_id.quantity != 0:
                total_wo_disc = line_id.price_unit * line_id.quantity

            if total_wo_disc != 0 and line_id.discount != 0:
                disc_amount = (total_wo_disc * line_id.discount) / 100

            if not line_id.product_id:
                raise UserError(msg1 % line_id.name)

            if line_id.price_subtotal <= 0 and line_id.reference_price <= 0:
                raise UserError(msg2 % line_id.product_id.display_name)

            if invoice_type_code == "02":
                if line_id.product_id.product_brand_id:
                    brand_name = str(line_id.product_id.product_brand_id.id)

                model_name = str(line_id.product_id.id)

            invoice_lines[item] = {}
            invoice_lines[item]["unitCode"] = line_id.uom_id.code
            invoice_lines[item]["Quantity"] = "{:.2f}".format(line_id.quantity)
            invoice_lines[item]["PricingReferencePriceAmount"] = line_id.reference_price
            invoice_lines[item]["LineExtensionAmount"] = line_id.price_subtotal
            invoice_lines[item]["MultiplierFactorNumeric"] = "{:.2f}".format(
                line_id.discount
            )
            invoice_lines[item]["AllowanceChargeAmount"] = disc_amount
            invoice_lines[item]["AllowanceChargeBaseAmount"] = total_wo_disc
            invoice_lines[item]["TaxesTotal"] = {}
            invoice_lines[item]["WithholdingTaxesTotal"] = {}
            invoice_lines[item]["StandardItemIdentification"] = str(
                line_id.product_id.id
            )
            invoice_lines[item] = line_id._get_line_taxes(invoice_lines[item])
            invoice_lines[item]["TaxesTotal"] = self._set_line_taxes_total(
                invoice_lines[item]["TaxesTotal"], line_id.price_subtotal
            )
            invoice_lines[item]["BrandName"] = brand_name
            invoice_lines[item]["ModelName"] = model_name
            invoice_lines[item]["ItemDescription"] = (
                line_id.product_id.name or line_id.name
            )
            invoice_lines[item][
                "InformationContentProviderParty"
            ] = line_id._get_information_content_provider_party_values()
            invoice_lines[item]["PriceAmount"] = line_id.price_unit
            item += 1

        for kit_line_id in self.mapped("product_set_sale_id"):
            reference_price = 0.00
            base = 0.00
            brand_name = False
            model_name = False

            if not kit_line_id.product_id:
                raise UserError(msg1 % line_id.name)

            if invoice_type_code == "02":
                if kit_line_id.product_id.product_brand_id:
                    brand_name = str(kit_line_id.product_id.product_brand_id.id)

                model_name = str(kit_line_id.product_id.id)

            invoice_lines[item] = {}
            invoice_lines[item]["unitCode"] = "94"
            invoice_lines[item]["Quantity"] = "{:.2f}".format(kit_line_id.product_qty)
            invoice_lines[item]["PricingReferencePriceAmount"] = 0.00
            invoice_lines[item]["LineExtensionAmount"] = 0.00
            invoice_lines[item]["MultiplierFactorNumeric"] = "0.00"
            invoice_lines[item]["AllowanceChargeAmount"] = 0.00
            invoice_lines[item]["AllowanceChargeBaseAmount"] = 0.00
            invoice_lines[item]["TaxesTotal"] = {}
            invoice_lines[item]["WithholdingTaxesTotal"] = {}
            invoice_lines[item]["StandardItemIdentification"] = str(
                kit_line_id.product_id.id
            )
            line_ids = self.filtered(lambda x: x.product_set_sale_id == kit_line_id)

            for line_id in line_ids:
                reference_price += line_id.reference_price
                base += line_id.price_subtotal
                invoice_lines[item] = line_id._get_line_taxes(invoice_lines[item])

            invoice_lines[item]["PricingReferencePriceAmount"] = reference_price
            invoice_lines[item]["LineExtensionAmount"] = base
            invoice_lines[item]["AllowanceChargeBaseAmount"] = base
            invoice_lines[item]["TaxesTotal"] = self._set_line_taxes_total(
                invoice_lines[item]["TaxesTotal"], base
            )
            invoice_lines[item]["BrandName"] = brand_name
            invoice_lines[item]["ModelName"] = model_name
            invoice_lines[item]["ItemDescription"] = kit_line_id.product_id.name
            invoice_lines[item]["PriceAmount"] = base / kit_line_id.product_qty
            item += 1

        return invoice_lines
