# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from base64 import b64decode
from datetime import datetime, timedelta
from lxml import etree
from requests import post, exceptions
from . import global_functions
from odoo import api, models, fields, SUPERUSER_ID, _
from odoo.exceptions import ValidationError, UserError

DIAN_TYPES = (
    "e-invoicing",
    "e-credit_note",
    "e-debit_note",
    "e-support_document",
    "e-support_document_credit_note",
)
DIAN_URL = {
    "wsdl1": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "wsdl2": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}
MSG_TIMEOUT = "DIAN service generates a timeout error."
MSG_ERROR1 = (
    "Unknown Error,\n\nStatus Code: %s,\nReason: %s\n\nContact with your administrator."
)
MSG_ERROR2 = "Unknown Error,\n\n%s\n\nContact with your administrator."


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.model
    def _default_send_invoice_to_dian(self):
        return self.env.user.company_id.send_invoice_to_dian or "0"

    @api.model
    def _default_operation_type(self):
        user_id = self.env.user
        view_operation_type_field = False

        if (
            user_id.has_group(
                "l10n_co_account_e_invoicing.group_view_operation_type_field"
            )
            and user_id.id != SUPERUSER_ID
        ):
            view_operation_type_field = True

        if "type" in self._context.keys():
            if self._context["type"] == "out_invoice" and not view_operation_type_field:
                return "10"
            elif self._context["type"] == "in_invoice":
                return "10"
            else:
                return False
        elif not view_operation_type_field:
            return "10"
        else:
            return False

    @api.model
    def _default_invoice_type_code(self):
        user_id = self.env.user
        view_invoice_type_field = False

        if (
            user_id.has_group(
                "l10n_co_account_e_invoicing.group_view_invoice_type_field"
            )
            and user_id.id != SUPERUSER_ID
        ):
            view_invoice_type_field = True

        if "type" in self._context.keys():
            if self._context["type"] == "out_invoice" and not view_invoice_type_field:
                return "01"
            elif self._context["type"] == "in_invoice":
                return "05"
            else:
                return False
        elif not view_invoice_type_field:
            return "01"
        else:
            return False

    @api.multi
    def _compute_warn_certificate(self):
        for inv in self:
            warn_remaining_certificate = False
            warn_inactive_certificate = False
            if inv.company_id.einvoicing_enabled:
                warn_inactive_certificate = True

            if (
                inv.company_id.certificate_file
                and inv.company_id.certificate_password
                and inv.company_id.certificate_date
            ):
                remaining_days = inv.company_id.certificate_remaining_days or 0
                today = fields.Date.context_today(inv)
                date_to = inv.company_id.certificate_date
                days = (date_to - today).days
                warn_inactive_certificate = False

                if days < remaining_days:
                    if days < 0:
                        warn_inactive_certificate = True
                    else:
                        warn_remaining_certificate = True

            inv.warn_inactive_certificate = warn_inactive_certificate
            inv.warn_remaining_certificate = warn_remaining_certificate

    @api.multi
    def _compute_sequence_resolution_id(self):
        for invoice_id in self:
            sequence_resolution = False
            sequence_id = invoice_id.journal_id.sequence_id

            if sequence_id.dian_type in ("e-invoicing", "e-support_document"):
                sequence_resolution = self.env["ir.sequence.date_range"].search(
                    [
                        ("sequence_id", "=", sequence_id.id),
                        ("active_resolution", "=", True),
                    ]
                )

                sequence_resolution_ids = self.env["ir.sequence.date_range"].search(
                    [("sequence_id", "=", sequence_id.id)]
                )

                for sequence_resolution_id in sequence_resolution_ids:
                    move_name = invoice_id.move_name or ""
                    number = move_name.replace(sequence_resolution_id.prefix or "", "")

                    if (
                        number.isnumeric()
                        and sequence_resolution_id.number_from <= int(number)
                        and int(number) <= sequence_resolution_id.number_to
                    ):
                        sequence_resolution = sequence_resolution_id

            invoice_id.sequence_resolution_id = sequence_resolution

    warn_remaining_certificate = fields.Boolean(
        string="Warn About Remainings?",
        compute="_compute_warn_certificate",
        store=False,
    )
    warn_inactive_certificate = fields.Boolean(
        string="Warn About Inactive Certificate?",
        compute="_compute_warn_certificate",
        store=False,
    )
    sequence_resolution_id = fields.Many2one(
        comodel_name="ir.sequence.date_range",
        string="Sequence Resolution",
        compute="_compute_sequence_resolution_id",
        store=False,
    )
    delivery_datetime = fields.Datetime(string="Delivery Datetime", copy=False)
    send_invoice_to_dian = fields.Selection(
        selection=[("0", "Immediately"), ("1", "Delayed")],
        string="Send Invoice to DIAN?",
        default=_default_send_invoice_to_dian,
        copy=False,
    )
    operation_type = fields.Selection(
        selection=[
            ("09", "AIU"),
            ("10", "Standard"),
            ("20", "Credit note that references an e-invoice"),
            ("22", "Credit note without reference to invoices"),
            ("30", "Debit note that references an e-invoice"),
            ("32", "Debit note without reference to invoices"),
        ],
        string="Operation Type",
        default=_default_operation_type,
        copy=False,
    )
    invoice_type_code = fields.Selection(
        selection=[
            ("01", "E-invoice of sale"),
            ("03", "E-document of transmission - type 03"),
            ("04", "E-invoice of sale - type 04"),
            ("05", "E-Support Document"),
        ],
        string="Invoice Type",
        default=_default_invoice_type_code,
        copy=False,
    )
    receipt_document_reference = fields.Char(
        string="Merchandise / Service Receipt Document", copy=False
    )
    dian_document_state = fields.Selection(
        selection=[
            ("dian_acceptance", "DIAN Acceptance"),
            ("dian_rejection", "DIAN Rejection"),
            ("e-invocie_receipt", "E-invoice Receipt"),
            ("as_receipt", "Assets and/or Services Receipt"),
            ("e-invocie_claim", "E-invoice Claim"),
            ("express_acceptance", "Express Acceptance"),
            ("tacit_acceptance", "Tacit Acceptance"),
        ],
        string="DIAN Document State",
        copy=False,
    )
    dian_document_mail_subject = fields.Char(string="Mail Subject", copy=False)
    supplier_uuid = fields.Char(string="Supplier CUFE", size=96)
    dian_claim = fields.Selection(
        selection=[
            ("01", "Documento con inconsistencias"),
            ("02", "Mercancía no entregada totalmente"),
            ("03", "Mercancía no entregada parcialmente"),
            ("04", "Servicio no prestado"),
        ],
        string="DIAN Claim",
    )
    dian_document_ids = fields.One2many(
        comodel_name="account.invoice.dian.document",
        inverse_name="invoice_id",
        string="DIAN Documents",
    )

    _sql_constraints = [
        (
            "supplier_uuid_unique",
            "unique(supplier_uuid)",
            _("The Supplier CUFE must be unique"),
        )
    ]

    @api.multi
    def update(self, values):
        res = super(AccountInvoice, self).update(values)

        for invoice_id in self:
            if invoice_id.type == "out_refund" and invoice_id.operation_type not in (
                "20",
                "22",
            ):
                invoice_id.operation_type = "20"
            elif (
                invoice_id.type == "out_invoice"
                and invoice_id.debit_invoice_id
                and invoice_id.operation_type not in ("30", "32")
            ):
                invoice_id.operation_type = "30"

        return res

    def _get_active_dian_resolution(self):
        msg = _(
            "You do not have an active dian resolution, contact with your "
            "administrator."
        )
        resolution_number = False

        if self.sequence_resolution_id:
            resolution_number = self.sequence_resolution_id.resolution_number
            date_from = self.sequence_resolution_id.date_from
            date_to = self.sequence_resolution_id.date_to_resolution
            prefix = self.sequence_resolution_id.prefix
            number_from = self.sequence_resolution_id.number_from
            number_to = self.sequence_resolution_id.number_to
            technical_key = self.sequence_resolution_id.technical_key

        if not resolution_number:
            raise UserError(msg)

        return {
            "InvoiceAuthorization": resolution_number,
            "StartDate": date_from,
            "EndDate": date_to,
            "Prefix": prefix,
            "From": number_from,
            "To": number_to,
            "technical_key": technical_key,
        }

    def _get_billing_reference(self):
        msg1 = _(
            "You can not make a refund invoice of an invoice with state different "
            "to 'Open' or 'Paid'."
        )
        msg2 = _(
            "You can not make a refund invoice of an invoice with DIAN documents "
            "with state 'Draft', 'Sent' or 'Cancelled'."
        )
        billing_reference = {
            "ID": False,
            "UUID": False,
            "IssueDate": False,
            "CustomizationID": False,
        }
        refund_invoice_id = self.refund_invoice_id or self.debit_invoice_id

        if refund_invoice_id:
            if refund_invoice_id.state not in ("open", "paid"):
                raise UserError(msg1)

            dian_document_states = refund_invoice_id.dian_document_ids.mapped("state")

            if (
                "done" not in dian_document_states
                or "draft" in dian_document_states
                or "sent" in dian_document_states
            ):
                raise UserError(msg2)

            if self.operation_type not in ("20", "30") and self.type not in (
                "in_refund",
                "in_invoice",
            ):
                return billing_reference

            for dian_document in refund_invoice_id.dian_document_ids:
                if dian_document.state == "done":
                    billing_reference["ID"] = refund_invoice_id.number
                    billing_reference["UUID"] = dian_document.cufe_cude
                    billing_reference["IssueDate"] = refund_invoice_id.date_invoice
                    billing_reference["CustomizationID"] = (
                        refund_invoice_id.operation_type
                    )
                    break

        return billing_reference

    def _get_payment_exchange_rate(self):
        date = self._get_currency_rate_date() or fields.Date.today()
        rate = self.currency_id._convert(
            1, self.company_id.currency_id, self.company_id, date
        )

        return {
            "SourceCurrencyBaseRate": rate,
            "TargetCurrencyCode": self.currency_id.name,
            "Date": date,
        }

    def _get_einvoicing_taxes(self):
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
        taxes = {}
        tax_total_base = 0
        withholding_taxes = {}

        for tax in self.tax_line_ids:
            if tax.tax_id.tax_group_id.is_einvoicing:
                if not tax.tax_id.tax_group_id.tax_group_type_id:
                    raise UserError(msg1 % tax.name)

                tax_code = tax.tax_id.tax_group_id.tax_group_type_id.code
                tax_name = tax.tax_id.tax_group_id.tax_group_type_id.name
                tax_type = tax.tax_id.tax_group_id.tax_group_type_id.type
                tax_percent = "{:.2f}".format(tax.tax_id.amount)
                tax_amount = tax.amount

                if tax_type == "withholding_tax" and tax.tax_id.amount == 0:
                    raise UserError(msg2 % tax.name)

                if tax_type == "tax" and tax.tax_id.amount <= 0:
                    raise UserError(msg3 % tax.name)

                if tax_amount != (tax.base * tax.tax_id.amount / 100):
                    tax_amount = tax.base * tax.tax_id.amount / 100

                if tax_type == "withholding_tax" and tax.tax_id.amount > 0:
                    if tax_code not in withholding_taxes:
                        withholding_taxes[tax_code] = {}
                        withholding_taxes[tax_code]["total"] = 0
                        withholding_taxes[tax_code]["name"] = tax_name
                        withholding_taxes[tax_code]["taxes"] = {}

                    if tax_percent not in withholding_taxes[tax_code]["taxes"]:
                        withholding_taxes[tax_code]["taxes"][tax_percent] = {}
                        withholding_taxes[tax_code]["taxes"][tax_percent]["base"] = 0
                        withholding_taxes[tax_code]["taxes"][tax_percent]["amount"] = 0

                    withholding_taxes[tax_code]["total"] += tax_amount * (-1)
                    withholding_taxes[tax_code]["taxes"][tax_percent][
                        "base"
                    ] += tax.base
                    withholding_taxes[tax_code]["taxes"][tax_percent][
                        "amount"
                    ] += tax_amount * (-1)
                elif tax_type == "withholding_tax" and tax.tax_id.amount < 0:
                    # TODO 3.0 Las retenciones se recomienda no enviarlas a la DIAN
                    # Solo las positivas que indicarian una autorretencion, Si la DIAN
                    # pide que se envien las retenciones, seria quitar o comentar este if
                    pass
                else:
                    if tax_code not in taxes:
                        taxes[tax_code] = {}
                        taxes[tax_code]["total"] = 0
                        taxes[tax_code]["name"] = tax_name
                        taxes[tax_code]["taxes"] = {}

                    if tax_percent not in taxes[tax_code]["taxes"]:
                        taxes[tax_code]["taxes"][tax_percent] = {}
                        taxes[tax_code]["taxes"][tax_percent]["base"] = 0
                        taxes[tax_code]["taxes"][tax_percent]["amount"] = 0

                    taxes[tax_code]["total"] += tax_amount
                    taxes[tax_code]["taxes"][tax_percent]["base"] += tax.base
                    tax_total_base += tax.base
                    taxes[tax_code]["taxes"][tax_percent]["amount"] += tax_amount

        if "01" not in taxes:
            taxes["01"] = {}
            taxes["01"]["total"] = 0
            taxes["01"]["name"] = "IVA"
            taxes["01"]["taxes"] = {}
            taxes["01"]["taxes"]["0.00"] = {}
            taxes["01"]["taxes"]["0.00"]["base"] = 0
            taxes["01"]["taxes"]["0.00"]["amount"] = 0

        if "04" not in taxes:
            taxes["04"] = {}
            taxes["04"]["total"] = 0
            taxes["04"]["name"] = "ICA"
            taxes["04"]["taxes"] = {}
            taxes["04"]["taxes"]["0.00"] = {}
            taxes["04"]["taxes"]["0.00"]["base"] = 0
            taxes["04"]["taxes"]["0.00"]["amount"] = 0

        if "03" not in taxes:
            taxes["03"] = {}
            taxes["03"]["total"] = 0
            taxes["03"]["name"] = "INC"
            taxes["03"]["taxes"] = {}
            taxes["03"]["taxes"]["0.00"] = {}
            taxes["03"]["taxes"]["0.00"]["base"] = 0
            taxes["03"]["taxes"]["0.00"]["amount"] = 0

        return {
            "TaxesTotal": taxes,
            "TaxesTotalBase": tax_total_base,
            "WithholdingTaxesTotal": withholding_taxes,
        }

    def _get_invoice_lines(self):
        linde_ids = self.invoice_line_ids.filtered(lambda x: not x.display_type)

        return linde_ids._get_invoice_lines(self.invoice_type_code)

    def set_invoice_lines_price_reference(self):
        for line_id in self.invoice_line_ids:
            percentage = 100
            margin_percentage = line_id.product_id.margin_percentage

            if line_id.product_id.reference_price > 0:
                reference_price = line_id.product_id.reference_price
            elif 0 < margin_percentage < 100:
                percentage = (percentage - margin_percentage) / 100
                reference_price = line_id.product_id.standard_price / percentage
            else:
                reference_price = 0

            line_id.write(
                {
                    "cost_price": line_id.product_id.standard_price,
                    "reference_price": reference_price,
                }
            )

        return True

    def set_edi_document(self, application_response_type=False):
        msg = _("You must set a delivery date.")

        for invoice_id in self:
            if not invoice_id.company_id.einvoicing_enabled:
                return True

            send_invoice_to_dian = True
            invoice_type_code_01_02 = True
            invoice_type_code_04 = False

            if application_response_type:
                invoice_id.action_GetXmlByDocumentKey(False)
                dian_document_id = invoice_id.dian_document_ids.filtered(
                    lambda d: d.application_response_type == application_response_type
                )

                if dian_document_id and dian_document_id.state == "done":
                    return True
                elif not dian_document_id:
                    dian_document_id = self.env["account.invoice.dian.document"].create(
                        {
                            "company_id": invoice_id.company_id.id,
                            "invoice_id": invoice_id.id,
                            "application_response_type": application_response_type,
                        }
                    )
            else:
                if invoice_id.journal_id.sequence_id.dian_type not in DIAN_TYPES:
                    return True

                if invoice_id.dian_document_ids.filtered(lambda d: d.state != "cancel"):
                    return True

                if (
                    invoice_id.company_id.automatic_delivery_datetime
                    and invoice_id.company_id.additional_hours_delivery_datetime
                    and not invoice_id.delivery_datetime
                ):
                    invoice_date = self.date_invoice
                    invoice_datetime = datetime(
                        invoice_date.year, invoice_date.month, invoice_date.day, 8
                    )
                    hours_added = timedelta(
                        hours=invoice_id.company_id.additional_hours_delivery_datetime
                    )
                    invoice_id.delivery_datetime = invoice_datetime + hours_added

                if not invoice_id.delivery_datetime:
                    raise UserError(msg)

                invoice_id.set_invoice_lines_price_reference()
                xml_filename = False
                zipped_filename = False
                ar_xml_filename = False
                ad_zipped_filename = False

                for dian_document_id in invoice_id.dian_document_ids:
                    xml_filename = dian_document_id.xml_filename
                    zipped_filename = dian_document_id.zipped_filename
                    ar_xml_filename = dian_document_id.ar_xml_filename
                    ad_zipped_filename = dian_document_id.ad_zipped_filename
                    break

                dian_document_obj = self.env["account.invoice.dian.document"]
                dian_document_id = dian_document_obj.create(
                    {
                        "invoice_id": invoice_id.id,
                        "company_id": invoice_id.company_id.id,
                        "xml_filename": xml_filename,
                        "zipped_filename": zipped_filename,
                        "ar_xml_filename": ar_xml_filename,
                        "ad_zipped_filename": ad_zipped_filename,
                    }
                )
                send_invoice_to_dian = invoice_id.send_invoice_to_dian == "0"
                invoice_type_code_01_02 = invoice_id.invoice_type_code in ("01", "02")
                invoice_type_code_04 = invoice_id.invoice_type_code == "04"

            set_files = dian_document_id.action_set_files()

            if send_invoice_to_dian:
                if set_files:
                    if invoice_type_code_01_02:
                        dian_document_id.action_send_zipped_file()
                    elif invoice_type_code_04:
                        dian_document_id.action_send_email()
                else:
                    dian_document_id.send_failure_email()

        return True

    @api.onchange("supplier_uuid")
    def _onchange_supplier_uuid(self):
        if self.supplier_uuid and self.invoice_type_code == "05":
            self.invoice_type_code = "01"

    @api.multi
    def action_ApplicationResponse_030(self):
        for invoice_id in self:
            invoice_id.set_edi_document("030")

        return True

    @api.multi
    def action_ApplicationResponse_031(self):
        for invoice_id in self:
            invoice_id.set_edi_document("031")

        return True

    @api.multi
    def action_ApplicationResponse_032(self):
        for invoice_id in self:
            invoice_id.set_edi_document("032")

        return True

    @api.multi
    def action_ApplicationResponse_033(self):
        for invoice_id in self:
            invoice_id.set_edi_document("033")

        return True

    @api.multi
    def action_ApplicationResponse_034(self):
        for invoice_id in self:
            invoice_id.set_edi_document("034")

        return True

    @api.multi
    def action_GetXmlByDocumentKey(self, attachment=True):
        wsdl = DIAN_URL["wsdl" + self.company_id.profile_execution_id]
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )
        xml_soap_values["trackId"] = self.supplier_uuid
        xml_soap_values["To"] = wsdl.replace("?wsdl", "")
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(xml_soap_values, "GetXmlByDocumentKey"),
            xml_soap_values["Id"],
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )
        timeout = 10

        for attempt in range(3):
            try:
                b = "http://schemas.datacontract.org/2004/07/EventResponse"
                cac = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                msg = _("You cannot send events to cash invoices.")
                XmlBytesBase64 = False
                response = post(
                    url=wsdl,
                    headers={
                        "Content-Type": "application/soap+xml",
                        "accept": "*/*",
                        "accept-encoding": "gzip, deflate",
                        "action": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetXmlByDocumentKey",
                    },
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    status_code = "other"
                    root = etree.fromstring(response.content)

                    for element in root.iter("{%s}Code" % b):
                        status_code = element.text

                    if status_code != "100":
                        continue

                    for element in root.iter("{%s}XmlBytesBase64" % b):
                        XmlBytesBase64 = element.text

                    if not XmlBytesBase64:
                        continue

                    if attachment:
                        self.env["ir.attachment"].create(
                            {
                                "name": self.supplier_uuid + ".xml",
                                "datas_fname": self.supplier_uuid + ".xml",
                                "type": "binary",
                                "datas": XmlBytesBase64,
                                "res_model": self._name,
                                "res_id": self.id,
                                "mimetype": "application/xml",
                            }
                        )
                    else:
                        xml = etree.fromstring(b64decode(XmlBytesBase64))

                        for element in xml.iter("{%s}PaymentMeans" % cac):
                            for subelement in element.iter("{%s}ID" % cbc):
                                if subelement.text != "2":
                                    raise UserError(msg)
                else:
                    raise ValidationError(
                        _(MSG_ERROR1) % (response.status_code, response.reason)
                    )

                break
            except exceptions.Timeout:
                if attempt < 2:
                    timeout += 10

                    continue
                else:
                    raise ValidationError(_(MSG_TIMEOUT))
            except exceptions.RequestException as e:
                raise ValidationError(_(MSG_ERROR2) % (e))

    @api.multi
    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()

        for invoice_id in self:
            if invoice_id.sequence_resolution_id:
                invoice_id.set_edi_document()
            elif invoice_id.supplier_uuid:
                invoice_id.action_ApplicationResponse_030()

        return res

    @api.multi
    def action_cancel(self):
        msg = _("You cannot cancel a invoice sent to the DIAN and that was approved.")
        res = super(AccountInvoice, self).action_cancel()
        allow_cancel_invoices = self.env.user.has_group(
            "l10n_co_account_e_invoicing.group_allow_cancel_invoices"
        )

        for invoice_id in self:
            dian_document_states = invoice_id.dian_document_ids.mapped("state")

            if "done" not in dian_document_states:
                invoice_id.dian_document_ids.write({"state": "cancel"})

                return res

            if not allow_cancel_invoices:
                raise UserError(msg)

        return res
