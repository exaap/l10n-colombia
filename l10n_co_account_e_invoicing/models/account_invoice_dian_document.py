# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

from dateutil import tz
from io import BytesIO
from datetime import datetime
from base64 import b64encode, b64decode
from zipfile import ZipFile
import ssl
from pytz import timezone
from qrcode import QRCode
from requests import post, exceptions
from lxml import etree
from . import global_functions
from odoo import models, api, fields, _
from odoo.exceptions import ValidationError, UserError

ssl._create_default_https_context = ssl._create_unverified_context

DIAN_URL = {
    "wsdl-hab": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "wsdl": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "catalogo-hab": "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey={}",
    "catalogo": "https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={}",
}
APPLICATION_RESPONSE = {
    "030": "Acuse de recibo de Factura Electrónica de Venta",
    "031": "Reclamo de la Factura Electrónica de Venta",
    "032": "Recibo del bien y/o prestación del servicio",
    "033": "Aceptación expresa",
    "034": "Aceptación Tácita",
}
DIAN_CLAIM = {
    "01": "Documento con inconsistencias",
    "02": "Mercancía no entregada totalmente",
    "03": "Mercancía no entregada parcialmente",
    "04": "Servicio no prestado",
}
MSG_TIMEOUT = "DIAN service generates a timeout error."
MSG_ERROR1 = (
    "Unknown Error,\n\nStatus Code: %s,\nReason: %s\n\nContact with your administrator."
)
MSG_ERROR2 = "Unknown Error,\n\n%s\n\nContact with your administrator."


class AccountInvoiceDianDocument(models.Model):
    _name = "account.invoice.dian.document"
    _order = "create_date desc"
    _description = "DIAN Document"

    def go_to_dian_document(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Dian Document",
            "view_type": "form",
            "view_mode": "form",
            "res_model": self._name,
            "res_id": self.id,
            "target": "current",
        }

    def _get_qr_data(self):
        if self.invoice_id.invoice_type_code == "05":
            supplier = self.invoice_id.partner_id
            customer = self.company_id.partner_id
        else:
            supplier = self.company_id.partner_id
            customer = self.invoice_id.partner_id

        AccountingSupplierParty = supplier._get_accounting_partner_party_values()
        AccountingCustomerParty = customer._get_accounting_partner_party_values()
        einvoicing_taxes = self.invoice_id._get_einvoicing_taxes()
        ValImp1 = einvoicing_taxes["TaxesTotal"]["01"]["total"]
        ValImp2 = einvoicing_taxes["TaxesTotal"]["04"]["total"]
        ValImp3 = einvoicing_taxes["TaxesTotal"]["03"]["total"]
        ValFac = self.invoice_id.amount_untaxed
        ValOtroIm = ValImp2 - ValImp3
        ValTolFac = ValFac + ValImp1 + ValOtroIm
        create_date = self.invoice_id.create_date
        qr_data = "NumFac: " + (self.invoice_id.number or _("WITHOUT VALIDATE"))
        qr_data += "\nFecFac: " + datetime.strftime(create_date, "%Y-%m-%d")
        qr_data += "\nHorFac: " + datetime.strftime(create_date, "%H:%M:%S-05:00")
        qr_data += "\nNitFac: " + (AccountingSupplierParty["CompanyID"] or "")
        qr_data += "\nDocAdq: " + (AccountingCustomerParty["CompanyID"] or "")
        qr_data += "\nValFac: " + "{:.2f}".format(ValFac)
        qr_data += "\nValIva: " + "{:.2f}".format(ValImp1)
        qr_data += "\nValOtroIm: " + "{:.2f}".format(ValOtroIm)
        qr_data += "\nValTolFac: " + "{:.2f}".format(ValTolFac)

        if self.cufe_cude:
            if (
                self.invoice_id.type == "out_invoice"
                and not self.invoice_id.debit_invoice_id
                and self.invoice_id.invoice_type_code != "03"
            ):
                qr_data += "\nCUFE: " + self.cufe_cude
            elif self.invoice_id.type == "out_refund" or (
                self.invoice_id.type == "out_invoice"
                and (
                    self.invoice_id.debit_invoice_id
                    or self.invoice_id.invoice_type_code == "03"
                )
            ):
                qr_data += "\nCUDE: " + self.cufe_cude
            elif self.invoice_id.type in ("in_invoice", "in_refund"):
                qr_data += "\nCUDS: " + self.cufe_cude

        qr_data += "\n\nURL: " + (self.invoice_url or "")

        return qr_data

    def _get_qrcode(self):
        qr_code = QRCode(version=4, box_size=4, border=1)
        qr_code.add_data(self._get_qr_data())
        qr_code.make(fit=True)
        image = qr_code.make_image()
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        return b64encode(buffer.getvalue())

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="State",
        readonly=True,
        default="draft",
    )
    company_id = fields.Many2one("res.company", string="Company")
    invoice_id = fields.Many2one("account.invoice", string="Invoice")
    issue_datetime = fields.Datetime(string="Issue Datetime", default=False)
    application_response_type = fields.Selection(
        selection=[
            ("030", "Acuse de recibo de Factura Electrónica de Venta"),
            ("031", "Reclamo de la Factura Electrónica de Venta"),
            ("032", "Recibo del bien y/o prestación del servicio"),
            ("033", "Aceptación expresa"),
            ("034", "Aceptación Tácita"),
        ],
        string="ApplicationResponse Type",
        default=False,
    )
    invoice_url = fields.Char(string="Invoice Url")
    cufe_cude_uncoded = fields.Char(string="CUFE/CUDE Uncoded")
    cufe_cude = fields.Char(string="CUFE/CUDE")
    software_security_code_uncoded = fields.Char(string="SoftwareSecurityCode Uncoded")
    software_security_code = fields.Char(string="SoftwareSecurityCode")
    profile_execution_id = fields.Selection(
        string="Destination Environment of Document",
        related="company_id.profile_execution_id",
        store=False,
    )
    xml_filename = fields.Char(string="Invoice XML Filename")
    xml_file = fields.Binary(string="Invoice XML File")
    zipped_filename = fields.Char(string="Zipped Filename")
    zipped_file = fields.Binary(string="Zipped File")
    ar_xml_filename = fields.Char(string="ApplicationResponse XML Filename")
    ar_xml_file = fields.Binary(string="ApplicationResponse XML File")
    validation_datetime = fields.Datetime(string="Validation Datetime", default=False)
    ad_zipped_filename = fields.Char(string="AttachedDocument Zipped Filename")
    ad_zipped_file = fields.Binary(string="AttachedDocument Zipped File")
    mail_sent = fields.Boolean(string="Mail Sent?")
    zip_key = fields.Char(string="ZipKey")
    get_status_zip_status_code = fields.Selection(
        selection=[
            ("00", "Processed Correctly"),
            ("66", "NSU not found"),
            ("90", "TrackId not found"),
            ("99", "Validations contain errors in mandatory fields"),
            ("other", "Other"),
        ],
        string="Status Code",
        default=False,
    )
    get_status_zip_response = fields.Text(string="Response")
    dian_document_line_ids = fields.One2many(
        comodel_name="account.invoice.dian.document.line",
        inverse_name="dian_document_id",
        string="DIAN Document Lines",
    )

    def _set_filenames(self):
        msg1 = _("The document type of '%s' is not NIT")
        msg2 = _("'%s' does not have a document type established.")
        msg3 = _("'%s' does not have a identification document established.")
        msg4 = _("There is no date range corresponding to the date of your invoice.")
        invoice_date = (
            datetime.strftime(self.invoice_id.date_invoice, "%Y-%m-%d %H:%M:%S")
            or fields.Date.today()
        )

        if self.company_id.partner_id.l10n_co_identification_type_code:
            if self.company_id.partner_id.l10n_co_identification_type_code != "31":
                raise UserError(msg1 % self.company_id.partner_id.name)
        else:
            raise UserError(msg2 % self.company_id.partner_id.name)

        if not self.company_id.partner_id.l10n_co_identification_document:
            raise UserError(msg3)

        daterange = self.env["date.range"].search(
            [("date_start", "<=", invoice_date), ("date_end", ">=", invoice_date)]
        )

        if (
            not daterange
            or daterange.company_id != self.company_id
            or not daterange.type_id
            or not daterange.type_id.name
        ):
            raise UserError(msg4)
        else:
            # Regla: el consecutivo se iniciará en “00000001” cada primero de enero.
            out_invoice_sent = daterange.out_invoice_sent
            out_refund_credit_sent = daterange.out_refund_credit_sent
            out_refund_debit_sent = daterange.out_refund_debit_sent
            in_invoice_sent = daterange.in_invoice_sent
            in_refund_sent = daterange.in_refund_sent
            application_response_sent = daterange.application_response_sent
            zip_out_sent = (
                out_invoice_sent + out_refund_credit_sent + out_refund_debit_sent
            )
            zip_in_sent = in_invoice_sent + in_refund_sent
            zip_ar_sent = application_response_sent

        # nnnnnnnnnn: NIT del Facturador Electrónico sin DV, de diez (10) dígitos
        # alineados a la derecha y relleno con ceros a la izquierda.
        nnnnnnnnnn = self.company_id.partner_id.l10n_co_identification_document.zfill(
            10
        )
        # El Código “ppp” es 000 para Software Propio
        ppp = "000"

        if self.company_id.have_technological_provider:
            ppp = self.company_id.assignment_code
        # aa: Dos (2) últimos dígitos año calendario
        aa = invoice_date[2:4]
        # dddddddd: consecutivo del paquete de archivos comprimidos enviados;
        # de ocho (8) dígitos decimales alineados a la derecha y ajustado a la
        # izquierda con ceros; en el rango:
        # 00000001 <= 99999999
        zdddddddd = str(zip_out_sent + 1).zfill(8)
        z_prefix = "z"
        ar_prefix = "ar"
        ad_prefix = "ad"
        debit_invoice_id = self.invoice_id.debit_invoice_id

        if self.invoice_id.type == "out_invoice" and not debit_invoice_id:
            xml_prefix = "fv"
            daterange.out_invoice_sent += 1
            dddddddd = str(daterange.out_invoice_sent)
        elif self.invoice_id.type == "out_refund":
            xml_prefix = "nc"
            daterange.out_refund_credit_sent += 1
            dddddddd = str(daterange.out_refund_credit_sent)
        elif self.invoice_id.type == "out_invoice" and debit_invoice_id:
            xml_prefix = "nd"
            daterange.out_refund_debit_sent += 1
            dddddddd = str(daterange.out_refund_debit_sent)
        elif self.invoice_id.supplier_uuid:
            xml_prefix = "ar"
            daterange.application_response_sent += 1
            dddddddd = str(daterange.application_response_sent)
            zdddddddd = str(zip_ar_sent + 1).zfill(8)
            z_prefix = "zar"
            ar_prefix = "arar"
            ad_prefix = "adar"
        elif self.invoice_id.type == "in_invoice":
            xml_prefix = "ds"
            daterange.in_invoice_sent += 1
            dddddddd = str(daterange.in_invoice_sent)
            zdddddddd = str(zip_in_sent + 1).zfill(8)
            z_prefix = "zs"
            ar_prefix = "ars"
            ad_prefix = "ads"
        elif self.invoice_id.type == "in_refund":
            xml_prefix = "nas"
            daterange.in_refund_sent += 1
            dddddddd = str(daterange.in_refund_sent)
            zdddddddd = str(zip_in_sent + 1).zfill(8)
            z_prefix = "zs"
            ar_prefix = "ars"
            ad_prefix = "ads"
        else:
            raise ValidationError("ERROR: TODO 2.0")

        dddddddd = dddddddd.zfill(8)
        nnnnnnnnnnpppaadddddddd = nnnnnnnnnn + ppp + aa + dddddddd
        zaradnnnnnnnnnnpppaadddddddd = nnnnnnnnnn + ppp + aa + zdddddddd
        self.write(
            {
                "xml_filename": xml_prefix + nnnnnnnnnnpppaadddddddd + ".xml",
                "zipped_filename": z_prefix + zaradnnnnnnnnnnpppaadddddddd + ".zip",
                "ar_xml_filename": ar_prefix + zaradnnnnnnnnnnpppaadddddddd + ".xml",
                "ad_zipped_filename": ad_prefix + zaradnnnnnnnnnnpppaadddddddd + ".zip",
            }
        )

        return True

    def _get_xml_values(self, ClTec):
        provider = self.company_id.partner_id
        supplier = self.company_id.partner_id
        customer = self.invoice_id.partner_id
        CodImp2 = "04"
        CodImp3 = "03"
        industry_ids = self.env["res.partner.industry"]
        industry_ids |= supplier.industry_id
        industry_ids |= supplier.secondary_industry_ids
        industry_ids = industry_ids.filtered(lambda x: x.type == "dian")
        industry_codes = industry_ids.mapped("code")
        IndustryClassificationCode = ";".join(industry_codes)

        if not self.invoice_id.payment_mean_code_id:
            self.invoice_id.payment_mean_code_id = (
                self.env["account.payment.mean.code"].search([("code", "=", "1")]).id
            )

        if self.company_id.have_technological_provider:
            provider = self.company_id.technological_provider_id

        if self.invoice_id.invoice_type_code == "05":
            supplier = self.invoice_id.partner_id
            customer = self.company_id.partner_id
            CodImp2 = False
            CodImp3 = False

        AccountingSupplierParty = supplier._get_accounting_partner_party_values()
        AccountingCustomerParty = customer._get_accounting_partner_party_values()
        IdSoftware = self.company_id.software_id
        SoftwarePIN = self.company_id.software_pin
        ID = self.invoice_id.number
        SoftwareSecurityCode = global_functions.get_SoftwareSecurityCode(
            IdSoftware, SoftwarePIN, ID
        )
        ProfileExecutionID = self.company_id.profile_execution_id

        if ProfileExecutionID == "1":
            QRCodeURL = DIAN_URL["catalogo"]
        else:
            QRCodeURL = DIAN_URL["catalogo-hab"]

        issue_datetime = self.issue_datetime
        IssueDate = datetime.strftime(issue_datetime, "%Y-%m-%d")
        IssueTime = datetime.strftime(issue_datetime, "%H:%M:%S-05:00")
        delivery_datetime = self.invoice_id.delivery_datetime
        ActualDeliveryDate = datetime.strftime(delivery_datetime, "%Y-%m-%d")
        ActualDeliveryTime = datetime.strftime(delivery_datetime, "%H:%M:%S-05:00")
        ValFac = self.invoice_id.amount_untaxed
        einvoicing_taxes = self.invoice_id._get_einvoicing_taxes()
        ValImp1 = einvoicing_taxes["TaxesTotal"]["01"]["total"]
        ValImp2 = einvoicing_taxes["TaxesTotal"]["04"]["total"]
        ValImp3 = einvoicing_taxes["TaxesTotal"]["03"]["total"]
        ValOtroIm = ValImp2 - ValImp3
        TaxInclusiveAmount = ValFac + ValImp1 + ValImp2 + ValImp3
        PaymentExchangeRate = self.invoice_id._get_payment_exchange_rate()
        rate = PaymentExchangeRate["SourceCurrencyBaseRate"]
        # El valor a pagar puede verse afectado, por anticipos, y descuentos y
        # cargos a nivel de factura
        PayableAmount = TaxInclusiveAmount
        UUID = global_functions.get_UUID(
            ID,
            IssueDate,
            IssueTime,
            str("{:.2f}".format(ValFac * rate)),
            "01",
            str("{:.2f}".format(ValImp1 * rate)),
            CodImp2,
            str("{:.2f}".format(ValImp2 * rate)),
            CodImp3,
            str("{:.2f}".format(ValImp3 * rate)),
            str("{:.2f}".format(TaxInclusiveAmount * rate)),
            AccountingSupplierParty["CompanyID"],
            AccountingCustomerParty["CompanyID"],
            ClTec,
            SoftwarePIN,
            ProfileExecutionID,
        )
        QRCodeURL = QRCodeURL.format(UUID["CUFE/CUDE/CUDS"])
        self.write(
            {
                "invoice_url": QRCodeURL,
                "cufe_cude_uncoded": UUID["CUFE/CUDE/CUDSUncoded"],
                "cufe_cude": UUID["CUFE/CUDE/CUDS"],
                "software_security_code_uncoded": (
                    SoftwareSecurityCode["SoftwareSecurityCodeUncoded"]
                ),
                "software_security_code": SoftwareSecurityCode["SoftwareSecurityCode"],
            }
        )

        return {
            "ProviderIDschemeID": provider.l10n_co_verification_digit,
            "ProviderIDschemeName": provider.l10n_co_identification_type_code,
            "ProviderID": provider.l10n_co_identification_document,
            "SoftwareID": IdSoftware,
            "SoftwareSecurityCode": SoftwareSecurityCode["SoftwareSecurityCode"],
            "QRCodeURL": QRCodeURL,
            "ProfileExecutionID": ProfileExecutionID,
            "ID": ID,
            "UUID": UUID["CUFE/CUDE/CUDS"],
            "IssueDate": IssueDate,
            "IssueTime": IssueTime,
            "ValIva": "{:.2f}".format(ValImp1),
            "ValOtroIm": "{:.2f}".format(ValOtroIm),
            "DueDate": self.invoice_id.date_due,
            "Note": self.invoice_id.comment or "",
            "LineCountNumeric": len(self.invoice_id.invoice_line_ids),
            "OrderReferenceID": self.invoice_id.name,
            "ReceiptDocumentReferenceID": self.invoice_id.receipt_document_reference,
            "IndustryClassificationCode": IndustryClassificationCode,
            "AccountingSupplierParty": AccountingSupplierParty,
            "AccountingCustomerParty": AccountingCustomerParty,
            "ActualDeliveryDate": ActualDeliveryDate,
            "ActualDeliveryTime": ActualDeliveryTime,
            "DeliveryTerms": {"LossRiskResponsibilityCode": False, "LossRisk": False},
            "PaymentMeansID": self.invoice_id.payment_mean_id.code,
            "PaymentMeansCode": self.invoice_id.payment_mean_code_id.code,
            "PaymentDueDate": self.invoice_id.date_due,
            "PaymentExchangeRate": PaymentExchangeRate,
            "TaxesTotal": einvoicing_taxes["TaxesTotal"],
            "WithholdingTaxesTotal": einvoicing_taxes["WithholdingTaxesTotal"],
            "LineExtensionAmount": self.invoice_id.amount_untaxed,
            "TaxExclusiveAmount": einvoicing_taxes["TaxesTotalBase"],
            "TaxInclusiveAmount": TaxInclusiveAmount,
            "PayableAmount": PayableAmount,
        }

    def _get_invoice_values(self):
        msg1 = _("Your journal: %s, has no a invoice sequence")
        msg2 = _(
            "Your active dian resolution has no technical key, contact with your "
            "administrator."
        )
        msg3 = _(
            "Your journal: %s, has no a invoice sequence with type equal to E-Invoicing"
        )
        msg4 = _(
            "Your journal: %s, has no a invoice sequence with type equal to "
            "Contingency Checkbook E-Invoicing"
        )
        msg5 = _("The invoice type selected is not valid to this invoice.")
        sequence_id = self.invoice_id.journal_id.sequence_id
        ClTec = False

        if not sequence_id:
            raise UserError(msg1 % self.invoice_id.journal_id.name)

        active_dian_resolution = self.invoice_id._get_active_dian_resolution()
        delivery = self.invoice_id.partner_shipping_id

        if self.invoice_id.invoice_type_code in ("01", "02"):
            ClTec = active_dian_resolution["technical_key"]

            if not ClTec:
                raise UserError(msg2)

        if self.invoice_id.invoice_type_code != "03":
            if sequence_id.dian_type != "e-invoicing":
                raise UserError(msg3 % self.invoice_id.journal_id.name)
        else:
            if sequence_id.dian_type != "contingency_checkbook_e-invoicing":
                raise UserError(msg4 % self.invoice_id.journal_id.name)

        if self.invoice_id.operation_type not in ("09", "10", "11"):
            raise UserError(msg5)

        xml_values = self._get_xml_values(ClTec)
        xml_values["InvoiceControl"] = active_dian_resolution
        # Punto 13.1.5.1. Documento Invoice – Factura electrónica
        # Anexo tecnico version 1.8
        # 10 Estándar
        # 09 AIU
        # 11 Mandatos
        # 12 Transporte
        # 13 Cambiario
        xml_values["CustomizationID"] = self.invoice_id.operation_type
        # Punto 13.1.3. Tipo de Documento: cbc:InvoiceTypeCode y cbc:CreditnoteTypeCode
        # Anexo tecnico version 1.8
        # 01 Factura electrónica de Venta
        # 02 Factura electrónica de venta ‐exportación
        # 03 Instrumento electrónico de transmisión – tipo 03
        # 04 Factura electrónica de Venta ‐ tipo 04
        xml_values["InvoiceTypeCode"] = self.invoice_id.invoice_type_code
        xml_values["Delivery"] = delivery._get_delivery_values()
        xml_values["InvoiceLines"] = self.invoice_id._get_invoice_lines()

        return xml_values

    def _get_credit_note_values(self):
        msg1 = _("Your journal: %s, has no a credit note sequence")
        msg2 = _(
            "Your journal: %s, has no a invoice sequence with type equal to E-Credit "
            "Note"
        )
        sequence_id = self.invoice_id.journal_id.refund_sequence_id
        sequence_id = sequence_id or self.invoice_id.journal_id.sequence_id

        if not sequence_id:
            raise UserError(msg1 % self.invoice_id.journal_id.name)

        if sequence_id.dian_type != "e-credit_note":
            raise UserError(msg2 % self.invoice_id.journal_id.name)

        xml_values = self._get_xml_values(False)
        billing_reference = self.invoice_id._get_billing_reference()
        delivery = self.invoice_id.partner_shipping_id
        # Punto 13.1.5.2. Documento CreditNote – Nota Crédito
        # Anexo tecnico version 1.8
        # 20 Nota Crédito que referencia una factura electrónica.
        # 22 Nota Crédito sin referencia a facturas.
        xml_values["CustomizationID"] = self.invoice_id.operation_type
        # TODO 2.0: Exclusivo en referencias a documentos (elementos DocumentReference)
        # Punto 13.1.3. Tipo de Documento: cbc:InvoiceTypeCode y cbc:CreditnoteTypeCode
        # Anexo tecnico version 1.8
        # 91 Nota Crédito
        xml_values["CreditNoteTypeCode"] = "91"
        xml_values["BillingReference"] = billing_reference
        xml_values["DiscrepancyReferenceID"] = billing_reference["ID"]
        xml_values["DiscrepancyResponseCode"] = self.invoice_id.reason_id.code
        xml_values["DiscrepancyDescription"] = self.invoice_id.reason_id.name
        xml_values["Delivery"] = delivery._get_delivery_values()
        xml_values["CreditNoteLines"] = self.invoice_id._get_invoice_lines()

        return xml_values

    def _get_debit_note_values(self):
        msg1 = _("Your journal: %s, has no a debit note sequence")
        msg2 = _(
            "Your journal: %s, has no a invoice sequence with type equal to E-Debit "
            "Note"
        )
        sequence_id = self.invoice_id.journal_id.debitnote_sequence_id
        sequence_id = sequence_id or self.invoice_id.journal_id.sequence_id

        if not sequence_id:
            raise UserError(msg1 % self.invoice_id.journal_id.name)

        if sequence_id.dian_type != "e-debit_note":
            raise UserError(msg2 % self.invoice_id.journal_id.name)

        xml_values = self._get_xml_values(False)
        billing_reference = self.invoice_id._get_billing_reference()
        delivery = self.invoice_id.partner_shipping_id
        # Punto 13.1.5.3. Documento DebitNote – Nota Débito
        # Anexo tecnico version 1.8
        # 30 Nota Débito que referencia una factura electrónica.
        # 32 Nota Débito sin referencia a facturas.
        xml_values["CustomizationID"] = self.invoice_id.operation_type
        # TODO 2.0: Exclusivo en referencias a documentos (elementos DocumentReference)
        # Punto 13.1.3. Tipo de Documento: cbc:InvoiceTypeCode y cbc:CreditnoteTypeCode
        # Anexo tecnico version 1.8
        # 92 Nota Débito
        # TODO 2.0: DebitNoteTypeCode no existe en DebitNote
        # xml_values['DebitNoteTypeCode'] = '92'
        xml_values["BillingReference"] = billing_reference
        xml_values["DiscrepancyReferenceID"] = billing_reference["ID"]
        xml_values["DiscrepancyResponseCode"] = self.invoice_id.reason_id.code
        xml_values["DiscrepancyDescription"] = self.invoice_id.reason_id.name
        xml_values["Delivery"] = delivery._get_delivery_values()
        xml_values["DebitNoteLines"] = self.invoice_id._get_invoice_lines()

        return xml_values

    def _get_application_response_values(self):
        provider = self.company_id.partner_id
        sender = self.company_id.partner_id
        receiver = self.invoice_id.partner_id

        if self.company_id.have_technological_provider:
            provider = self.company_id.technological_provider_id

        SoftwareProvider = {
            "ProviderIDschemeID": provider.l10n_co_verification_digit,
            "ProviderIDschemeName": provider.l10n_co_identification_type_code,
            "ProviderID": provider.l10n_co_identification_document,
            "SoftwareID": self.company_id.software_id,
        }
        SoftwarePIN = self.company_id.software_pin
        ResponseCode = self.application_response_type
        DocumentReference = {
            "ID": self.invoice_id.reference,
            "UUID": self.invoice_id.supplier_uuid,
            "DocumentTypeCode": self.invoice_id.invoice_type_code or "01",
        }

        if ResponseCode == "030":
            ID = "ARFE"
        elif ResponseCode == "031":
            ID = "RFE"
        elif ResponseCode == "032":
            ID = "ARBS"
        elif ResponseCode == "033":
            ID = "AE"
        elif ResponseCode == "034":
            ID = "AT"

        ID += receiver.l10n_co_identification_document + DocumentReference["ID"]
        SoftwareSecurityCode = global_functions.get_SoftwareSecurityCode(
            SoftwareProvider["SoftwareID"], SoftwarePIN, ID
        )
        ProfileExecutionID = self.company_id.profile_execution_id

        if ProfileExecutionID == "1":
            QRCodeURL = DIAN_URL["catalogo"]
        else:
            QRCodeURL = DIAN_URL["catalogo-hab"]

        QRCodeURL = QRCodeURL.format(DocumentReference["UUID"])
        issue_datetime = self.issue_datetime
        IssueDate = datetime.strftime(issue_datetime, "%Y-%m-%d")
        IssueTime = datetime.strftime(issue_datetime, "%H:%M:%S-05:00")
        SenderParty = sender._get_accounting_partner_party_values()
        ReceiverParty = receiver._get_accounting_partner_party_values()
        UUID = global_functions.get_ApplicationResponseUUID(
            ID,
            IssueDate,
            IssueTime,
            SenderParty["CompanyID"],
            ReceiverParty["CompanyID"],
            ResponseCode,
            DocumentReference["ID"],
            DocumentReference["DocumentTypeCode"],
            SoftwarePIN,
        )
        ResponseCodename = False
        ResponseCodeListID = False

        if self.invoice_id.dian_claim:
            ResponseCodename = DIAN_CLAIM[self.invoice_id.dian_claim]
            ResponseCodeListID = self.invoice_id.dian_claim

        self.write(
            {
                "invoice_url": QRCodeURL,
                "cufe_cude_uncoded": UUID["CUDEUncoded"],
                "cufe_cude": UUID["CUDE"],
                "software_security_code_uncoded": (
                    SoftwareSecurityCode["SoftwareSecurityCodeUncoded"]
                ),
                "software_security_code": SoftwareSecurityCode["SoftwareSecurityCode"],
            }
        )

        return {
            "SoftwareProvider": SoftwareProvider,
            "SoftwareSecurityCode": SoftwareSecurityCode["SoftwareSecurityCode"],
            "QRCode": QRCodeURL,
            "ProfileExecutionID": ProfileExecutionID,
            "ID": ID,
            "UUID": UUID["CUDE"],
            "IssueDate": IssueDate,
            "IssueTime": IssueTime,
            "Note": False,
            "SenderParty": SenderParty,
            "ReceiverParty": ReceiverParty,
            "Response": {
                "ResponseCodename": ResponseCodename,
                "ResponseCodeListID": ResponseCodeListID,
                "ResponseCode": ResponseCode,
                "Description": APPLICATION_RESPONSE[ResponseCode],
            },
            "DocumentReference": DocumentReference,
            "IssuerParty": {
                "IDschemeID": self.create_uid.partner_id.l10n_co_verification_digit,
                "IDschemeName": self.create_uid.partner_id.l10n_co_identification_type_code,
                "ID": self.create_uid.partner_id.l10n_co_identification_document,
                "FirstName": self.create_uid.partner_id.firstname,
                "FamilyName": self.create_uid.partner_id.lastname,
                "JobTitle": False,
                "OrganizationDepartment": False,
            },
        }

    def _get_support_document_values(self):
        msg1 = _("Your journal: %s, has no a invoice sequence")
        msg2 = _(
            "Your journal: %s, has no a invoice sequence with type equal to E-Support "
            "Document"
        )
        sequence_id = self.invoice_id.journal_id.sequence_id

        if not sequence_id:
            raise UserError(msg1 % self.invoice_id.journal_id.name)

        if sequence_id.dian_type != "e-support_document":
            raise UserError(msg2 % self.invoice_id.journal_id.name)

        active_dian_resolution = self.invoice_id._get_active_dian_resolution()
        xml_values = self._get_xml_values(False)
        xml_values["InvoiceControl"] = active_dian_resolution
        # Punto 16.1.4.1 Procedencia de Vendedor - Anexo tecnico DS version 1.1
        # 10 Residente
        # 11 No Residente
        xml_values["CustomizationID"] = "11"
        xml_values["DV"] = False

        if self.invoice_id.partner_id.l10n_co_identification_type_code in (
            "11",
            "12",
            "13",
            "31",
        ):
            xml_values["CustomizationID"] = "10"
            xml_values["DV"] = str(
                self.invoice_id.partner_id._compute_verification_digit()
            )

        # Punto 16.1.3 Tipo de Documento - Anexo tecnico DS version 1.1
        # 05 Documento soporte en adquisiciones efectuadas a sujetos no obligados a
        # expedir factura o documento equivalente
        xml_values["InvoiceTypeCode"] = self.invoice_id.invoice_type_code
        xml_values["InvoiceLines"] = self.invoice_id._get_invoice_lines()

        return xml_values

    def _get_support_document_credit_note_values(self):
        msg1 = _("Your journal: %s, has no a credit note sequence")
        msg2 = _(
            "Your journal: %s, has no a invoice sequence with type equal to E-Support "
            "Document Credit Note"
        )
        sequence_id = self.invoice_id.journal_id.refund_sequence_id
        sequence_id = sequence_id or self.invoice_id.journal_id.sequence_id

        if not sequence_id:
            raise UserError(msg1 % self.invoice_id.journal_id.name)

        if sequence_id.dian_type != "e-support_document_credit_note":
            raise UserError(msg2 % self.invoice_id.journal_id.name)

        xml_values = self._get_xml_values(False)
        billing_reference = self.invoice_id._get_billing_reference()
        # Punto 16.1.4.1 Procedencia de Vendedor - Anexo tecnico DS version 1.1
        # 10 Residente
        # 11 No Residente
        xml_values["CustomizationID"] = "11"
        xml_values["DV"] = False

        if self.invoice_id.partner_id.l10n_co_identification_type_code in (
            "11",
            "12",
            "13",
            "31",
        ):
            xml_values["CustomizationID"] = "10"
            xml_values["DV"] = str(
                self.invoice_id.partner_id._compute_verification_digit()
            )

        # TODO 2.0: Exclusivo en referencias a documentos (elementos DocumentReference)
        # Punto 16.1.3 Tipo de Documento - Anexo tecnico DS version 1.1
        # 95 Nota de ajuste al documento soporte en adquisiciones efectuadas a sujetos
        # no obligados a expedir factura o documento equivalente
        xml_values["CreditNoteTypeCode"] = "95"
        xml_values["BillingReference"] = billing_reference
        xml_values["DiscrepancyReferenceID"] = billing_reference["ID"]
        xml_values["DiscrepancyResponseCode"] = self.invoice_id.reason_id.code
        xml_values["DiscrepancyDescription"] = self.invoice_id.reason_id.name
        xml_values["CreditNoteLines"] = self.invoice_id._get_invoice_lines()

        return xml_values

    def _get_xml_file(self):
        debit_invoice_id = self.invoice_id.debit_invoice_id

        if self.invoice_id.type == "out_invoice" and not debit_invoice_id:
            xml_without_signature = global_functions.get_template_xml(
                self._get_invoice_values(), "Invoice"
            )
        elif self.invoice_id.type == "out_refund":
            xml_without_signature = global_functions.get_template_xml(
                self._get_credit_note_values(), "CreditNote"
            )
        elif self.invoice_id.type == "out_invoice" and debit_invoice_id:
            xml_without_signature = global_functions.get_template_xml(
                self._get_debit_note_values(), "DebitNote"
            )
        elif self.invoice_id.supplier_uuid:
            xml_without_signature = global_functions.get_template_xml(
                self._get_application_response_values(), "ApplicationResponse"
            )
        elif self.invoice_id.type == "in_invoice":
            xml_without_signature = global_functions.get_template_xml(
                self._get_support_document_values(), "InvoiceDS"
            )
        elif self.invoice_id.type == "in_refund":
            xml_without_signature = global_functions.get_template_xml(
                self._get_support_document_credit_note_values(), "CreditNoteDS"
            )
        else:
            raise ValidationError("ERROR: TODO 2.0")

        xml_with_signature = global_functions.get_xml_with_signature(
            xml_without_signature,
            self.company_id.signature_policy_url,
            self.company_id.signature_policy_file,
            self.company_id.signature_policy_description,
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )

        return xml_with_signature

    def _get_zipped_file(self):
        output = BytesIO()
        zipfile = ZipFile(output, mode="w")
        zipfile_content = BytesIO()
        xml_file = self._get_xml_file()
        zipfile_content.write(b64decode(xml_file))
        zipfile.writestr(self.xml_filename, zipfile_content.getvalue())
        zipfile.close()

        return output.getvalue()

    def _get_dian_document_mail_subject(self):
        if self.application_response_type:
            ResponseCode = self.application_response_type
            DocumentReferenceID = self.invoice_id.reference

            if ResponseCode == "030":
                prefix = "ARFE"
            elif ResponseCode == "031":
                prefix = "RFE"
            elif ResponseCode == "032":
                prefix = "ARBS"
            elif ResponseCode == "033":
                prefix = "AE"
            elif ResponseCode == "034":
                prefix = "AT"

            return (
                "Evento;"
                + DocumentReferenceID
                + ";"
                + self.company_id.partner_id.l10n_co_identification_document
                + ";"
                + self.company_id.name
                + ";"
                + prefix
                + self.invoice_id.partner_id.l10n_co_identification_document
                + DocumentReferenceID
                + ";"
                + ResponseCode
                + ";"
            )
        else:
            return (
                self.company_id.partner_id.l10n_co_identification_document
                + ";"
                + self.company_id.name
                + ";"
                + self.invoice_id.number
                + ";"
                + self.invoice_id.invoice_type_code
                + ";"
                + self.invoice_id.partner_id.name
                + ";"
            )

    def action_set_files(self):
        if self.application_response_type:
            if self.invoice_id.dian_document_ids.filtered(
                lambda d: d.application_response_type == self.application_response_type
                and d.state == "done"
            ):
                self.unlink()

        if self.invoice_id.warn_inactive_certificate:
            raise ValidationError(_("There is no an active certificate."))

        if not self.validation_datetime:
            to_zone = tz.gettz(timezone("America/Bogota").zone)
            issue_datetime = datetime.now(to_zone).replace(hour=8, minute=0, second=0)
            self.issue_datetime = issue_datetime.strftime("%Y-%m-%d %H:%M:%S")

        if not self.xml_filename or not self.zipped_filename:
            self._set_filenames()

        xml_file = self._get_xml_file()

        if xml_file:
            self.xml_file = xml_file
            self.zipped_file = self._get_zipped_file()
        else:
            return xml_file

        return True

    def _get_ad_xml_values(self):
        ProfileExecutionID = self.company_id.profile_execution_id
        ad_zipped_filename = self.ad_zipped_filename
        ID = ad_zipped_filename.replace(".zip", "")
        to_zone = tz.gettz(timezone("America/Bogota").zone)
        issue_datetime = datetime.now(to_zone)  # .replace(hour=8, minute=0, second=0)
        IssueDate = issue_datetime.strftime("%Y-%m-%d")
        IssueTime = issue_datetime.strftime("%H:%M:%S-05:00")
        DocumentReferenceID = ""

        if self.invoice_id.type == "out_invoice":
            UUIDschemeName = "CUFE"
        elif self.invoice_id.type in ["in_invoice", "in_refund"]:
            UUIDschemeName = "CUDS"
        else:
            UUIDschemeName = "CUDE"

        if self.invoice_id.supplier_uuid:
            ParentDocumentID = (
                self.invoice_id.partner_id.l10n_co_identification_document
                + self.invoice_id.reference
            )
            UUIDschemeName = "CUDE"

            if self.application_response_type == "030":
                DocumentReferenceID = "ARFE"
            elif self.application_response_type == "031":
                DocumentReferenceID = "RFE"
            elif self.application_response_type == "032":
                DocumentReferenceID = "ARBS"
            elif self.application_response_type == "033":
                DocumentReferenceID = "AE"
            elif self.application_response_type == "034":
                DocumentReferenceID = "AT"
        else:
            ParentDocumentID = self.invoice_id.number

        UUID = self.cufe_cude
        sender = self.company_id.partner_id
        receiver = self.invoice_id.partner_id
        Attachment = b64decode(self.xml_file).decode("utf-8")
        DocumentReferenceID += ParentDocumentID

        if self.ar_xml_file:
            ApplicationResponse = b64decode(self.ar_xml_file).decode("utf-8")
        else:
            ApplicationResponse = "NO ApplicationResponse"

        validation_datetime = self.validation_datetime
        ValidationDate = datetime.strftime(validation_datetime, "%Y-%m-%d")
        ValidationTime = datetime.strftime(validation_datetime, "%H:%M:%S-05:00")

        return {
            "ProfileExecutionID": ProfileExecutionID,
            "ID": ID,
            "IssueDate": IssueDate,
            "IssueTime": IssueTime,
            "ParentDocumentID": ParentDocumentID,
            "SenderParty": sender._get_accounting_partner_party_values(),
            "ReceiverParty": receiver._get_accounting_partner_party_values(),
            "Attachment": Attachment,
            "DocumentReference": {
                "ID": DocumentReferenceID,
                "UUIDschemeName": UUIDschemeName,
                "UUID": UUID,
                "IssueDate": ValidationDate,
                "Attachment": ApplicationResponse,
                "ValidationDate": ValidationDate,
                "ValidationTime": ValidationTime,
            },
        }

    def _get_ad_xml_file(self):
        return global_functions.get_template_xml(
            self._get_ad_xml_values(), "AttachedDocument"
        )

    def _get_ad_zipped_file(self):
        ad_zipped_filename = self.ad_zipped_filename
        ad_xml_filename = ad_zipped_filename.replace(".zip", ".xml")
        output = BytesIO()
        zipfile = ZipFile(output, mode="w")
        zipfile_content = BytesIO()
        zipfile_content.write(self._get_ad_xml_file())
        zipfile.writestr(ad_xml_filename, zipfile_content.getvalue())

        if not self.invoice_id.supplier_uuid:
            zipfile_content = BytesIO()
            zipfile_content.write(b64decode(self._get_pdf_file()))
            zipfile.writestr(
                self.invoice_id.number + ".pdf", zipfile_content.getvalue()
            )

        zipfile.close()

        return b64encode(output.getvalue())

    def action_set_ad_zipped_file(self):
        ad_zipped_file = self._get_ad_zipped_file()

        if ad_zipped_file:
            self.write({"ad_zipped_file": ad_zipped_file})
        else:
            return ad_zipped_file

        return True

    def _get_SendTestSetAsync_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )
        xml_soap_values["fileName"] = self.zipped_filename.replace(".zip", "")
        xml_soap_values["contentFile"] = b64encode(self.zipped_file).decode("utf-8")
        xml_soap_values["testSetId"] = self.company_id.test_set_id

        return xml_soap_values

    def _get_SendBillSync_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )
        xml_soap_values["fileName"] = self.zipped_filename.replace(".zip", "")
        xml_soap_values["contentFile"] = b64encode(self.zipped_file).decode("utf-8")

        return xml_soap_values

    def _get_pdf_file(self):
        template_id = self.env["ir.actions.report"].browse(
            self.company_id.report_template.id
        )
        pdf = template_id.render_qweb_pdf([self.invoice_id.id])[0]
        b64_pdf = b64encode(pdf).decode("utf-8")

        return b64_pdf

    @api.multi
    def action_send_email(self):
        if not self.invoice_id.number:
            raise UserError(_("Your invoice has not been validated"))

        self.invoice_id.write(
            {"dian_document_mail_subject": self._get_dian_document_mail_subject()}
        )
        template_id = self.env["mail.template"].browse(
            self.env.ref("l10n_co_account_e_invoicing.email_template_for_einvoice").id
        )
        mail_id = template_id.send_mail(self.id, force_send=True)
        mail_id = self.env["mail.mail"].browse(mail_id)

        if mail_id.state == "sent":
            self.mail_sent = True
            mail_id.sudo().unlink()

        return True

    @api.multi
    def send_failure_email(self):
        msg1 = _(
            "The notification group for e-invoice failures is not set.\n"
            "You won't be notified if something goes wrong.\n"
            "Please go to Settings > Company > Notification Group."
        )
        subject = _("ALERT! Invoice %s was not sent to DIAN.") % self.invoice_id.number
        msg_body = _(
            """Cordial Saludo,<br/><br/>La factura """
            + self.invoice_id.number
            + """ del cliente """
            + self.invoice_id.partner_id.name
            + """ no pudo ser """
            """enviada a la Dian según el protocolo establecido previamente. Por """
            """favor revise el estado de la misma en el menú Documentos Dian e """
            """intente reprocesarla según el procedimiento definido."""
            """<br/>""" + self.company_id.name + """."""
        )
        email_ids = self.company_id.notification_group_ids

        if email_ids:
            email_to = ""

            for mail_id in email_ids:
                email_to += mail_id.email.strip() + ","
        else:
            raise UserError(msg1)

        mail_obj = self.env["mail.mail"]
        msg_vals = {"subject": subject, "email_to": email_to, "body_html": msg_body}
        msg_id = mail_obj.create(msg_vals)
        msg_id.send()

        return True

    def _get_status_response(self, response, send_email):
        b = "http://schemas.datacontract.org/2004/07/DianResponse"
        c = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
        s = "http://www.w3.org/2003/05/soap-envelope"
        to_return = True
        strings = ""
        status_code = "other"
        root = etree.fromstring(response.content)

        for element in root.iter("{%s}StatusCode" % b):
            if element.text in ("0", "00", "66", "90", "99"):
                if self.invoice_id.supplier_uuid:
                    if element.text == "00":
                        self.write({"state": "done"})

                        if self.application_response_type == "030":
                            dian_document_state = "e-invocie_receipt"
                        elif self.application_response_type == "031":
                            dian_document_state = "e-invocie_claim"
                        elif self.application_response_type == "032":
                            dian_document_state = "as_receipt"
                        elif self.application_response_type == "033":
                            dian_document_state = "express_acceptance"
                        elif self.application_response_type == "034":
                            dian_document_state = "tacit_acceptance"

                        self.invoice_id.write(
                            {"dian_document_state": dian_document_state}
                        )
                elif element.text == "00":
                    self.write({"state": "done"})
                    self.invoice_id.write({"dian_document_state": "dian_acceptance"})
                elif element.text == "99":
                    self.invoice_id.write({"dian_document_state": "dian_rejection"})

                status_code = element.text

        if status_code == "0":
            return self._get_GetStatus(send_email)

        if status_code == "00":
            for element in root.iter("{%s}StatusMessage" % b):
                strings = element.text

            for element in root.iter("{%s}XmlBase64Bytes" % b):
                self.write(
                    {
                        "ar_xml_file": element.text,
                        "validation_datetime": datetime.now().replace(
                            tzinfo=timezone("UTC")
                        ),
                    }
                )

            self.action_set_ad_zipped_file()

            if not self.mail_sent and send_email:
                self.action_send_email()

            to_return = True
        else:
            if send_email:
                self.send_failure_email()

            to_return = False

        for element in root.iter("{%s}string" % c):
            if strings == "":
                strings = "- " + element.text
            else:
                strings += "\n\n- " + element.text

        if strings == "":
            for element in root.iter("{%s}Body" % s):
                strings = etree.tostring(
                    element, xml_declaration=False, encoding="UTF-8"
                ).decode("utf-8")

            if strings == "":
                strings = etree.tostring(
                    root, xml_declaration=False, encoding="UTF-8"
                ).decode("utf-8")

        self.write(
            {
                "get_status_zip_status_code": status_code,
                "get_status_zip_response": strings,
            }
        )

        return to_return

    def _get_GetStatusZip_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )

        xml_soap_values["trackId"] = self.zip_key

        return xml_soap_values

    def action_GetStatusZip(self):
        wsdl = DIAN_URL["wsdl-hab"]

        if self.company_id.profile_execution_id == "1":
            wsdl = DIAN_URL["wsdl"]

        GetStatusZip_values = self._get_GetStatusZip_values()
        GetStatusZip_values["To"] = wsdl.replace("?wsdl", "")
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(GetStatusZip_values, "GetStatusZip"),
            GetStatusZip_values["Id"],
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )
        timeout = 10

        for attempt in range(3):
            try:
                response = post(
                    wsdl,
                    headers={"content-type": "application/soap+xml;charset=utf-8"},
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    self._get_status_response(response, True)
                elif response.status_code in (403, 500, 503, 507, 508):
                    self.env["account.invoice.dian.document.line"].create(
                        {
                            "dian_document_id": self.id,
                            "send_async_status_code": response.status_code,
                            "send_async_reason": response.reason,
                            "send_async_response": response.text,
                        }
                    )
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

        return True

    def action_SendBillSync_SendTestSetAsync(self):
        if self._get_GetStatus(False):
            return True

        msg1 = _(
            "Unknown Error,\n\nStatus Code: %s,\nReason: %s,\n\nContact with your administrator "
            "or you can choose a journal with a Contingency Checkbook E-Invoicing sequence "
            "and change the Invoice Type to 'E-document of transmission - type 03'."
        )
        msg2 = _(
            "Unknown Error,\n\n%s\n\nContact with your administrator "
            "or you can choose a journal with a Contingency Checkbook E-Invoicing sequence "
            "and change the Invoice Type to 'E-document of transmission - type 03'."
        )
        b = "http://schemas.datacontract.org/2004/07/UploadDocumentResponse"
        wsdl = DIAN_URL["wsdl-hab"]

        if self.company_id.profile_execution_id == "1":
            wsdl = DIAN_URL["wsdl"]
            SendBillSync_values = self._get_SendBillSync_values()
            SendBillSync_values["To"] = wsdl.replace("?wsdl", "")
            xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
                global_functions.get_template_xml(SendBillSync_values, "SendBillSync"),
                SendBillSync_values["Id"],
                self.company_id.certificate_file,
                self.company_id.certificate_password,
            )
        else:
            SendTestSetAsync_values = self._get_SendTestSetAsync_values()
            SendTestSetAsync_values["To"] = wsdl.replace("?wsdl", "")
            xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
                global_functions.get_template_xml(
                    SendTestSetAsync_values, "SendTestSetAsync"
                ),
                SendTestSetAsync_values["Id"],
                self.company_id.certificate_file,
                self.company_id.certificate_password,
            )

        timeout = 10

        for attempt in range(3):
            try:
                response = post(
                    wsdl,
                    headers={"content-type": "application/soap+xml;charset=utf-8"},
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    self.write({"state": "sent"})

                    if self.company_id.profile_execution_id == "1":
                        self._get_status_response(response, True)
                    else:
                        root = etree.fromstring(response.text.encode("utf-8"))

                        for element in root.iter("{%s}ZipKey" % b):
                            self.write({"zip_key": element.text})
                            self.action_GetStatusZip()
                elif response.status_code in (403, 500, 503, 507, 508):
                    self.env["account.invoice.dian.document.line"].create(
                        {
                            "dian_document_id": self.id,
                            "send_async_status_code": response.status_code,
                            "send_async_reason": response.reason,
                            "send_async_response": response.text,
                        }
                    )
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

        return True

    def _get_SendEventUpdateStatus_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )
        xml_soap_values["contentFile"] = b64encode(self.zipped_file).decode("utf-8")

        return xml_soap_values

    def action_SendEventUpdateStatus(self):
        b = "http://schemas.datacontract.org/2004/07/DianResponse"
        wsdl = DIAN_URL["wsdl-hab"]

        if self.company_id.profile_execution_id == "1":
            wsdl = DIAN_URL["wsdl"]

        SendEventUpdateStatus_values = self._get_SendEventUpdateStatus_values()
        SendEventUpdateStatus_values["To"] = wsdl.replace("?wsdl", "")
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(
                SendEventUpdateStatus_values, "SendEventUpdateStatus"
            ),
            SendEventUpdateStatus_values["Id"],
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )
        timeout = 10

        for attempt in range(3):
            try:
                response = post(
                    url=wsdl,
                    headers={
                        "Content-Type": "application/soap+xml",
                        "accept": "*/*",
                        "accept-encoding": "gzip, deflate",
                        "action": "http://wcf.dian.colombia/IWcfDianCustomerServices/SendEventUpdateStatus",
                    },
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    self.write({"state": "sent"})
                    self._get_status_response(response, False)
                elif response.status_code in (403, 500, 503, 507, 508):
                    self.env["account.invoice.dian.document.line"].create(
                        {
                            "dian_document_id": self.id,
                            "send_async_status_code": response.status_code,
                            "send_async_reason": response.reason,
                            "send_async_response": response.text,
                        }
                    )
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

        return True

    def action_send_zipped_file(self):
        if self.action_set_files():
            if self.invoice_id.supplier_uuid:
                self.action_SendEventUpdateStatus()
            else:
                self.action_SendBillSync_SendTestSetAsync()

        return True

    def _get_GetStatus_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )

        xml_soap_values["trackId"] = self.cufe_cude

        return xml_soap_values

    def _get_GetStatus(self, send_email):
        wsdl = DIAN_URL["wsdl-hab"]

        if self.company_id.profile_execution_id == "1":
            wsdl = DIAN_URL["wsdl"]

        GetStatus_values = self._get_GetStatus_values()
        GetStatus_values["To"] = wsdl.replace("?wsdl", "")
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(GetStatus_values, "GetStatus"),
            GetStatus_values["Id"],
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )
        timeout = 10

        for attempt in range(3):
            try:
                response = post(
                    url=wsdl,
                    headers={
                        "Content-Type": "application/soap+xml",
                        "accept": "*/*",
                        "accept-encoding": "gzip, deflate",
                        "action": "http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatus",
                    },
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    return self._get_status_response(response, send_email)
                elif response.status_code in (403, 500, 503, 507, 508):
                    self.env["account.invoice.dian.document.line"].create(
                        {
                            "dian_document_id": self.id,
                            "send_async_status_code": response.status_code,
                            "send_async_reason": response.reason,
                            "send_async_response": response.text,
                        }
                    )
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

    def action_GetStatus_without_send_email(self):
        return self._get_GetStatus(False)

    def action_process(self):
        if self.action_set_files():
            self.action_send_zipped_file()
        else:
            self.send_failure_email()

        return True

    # TODO: 2.0
    def _get_SendBillAttachmentAsync_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.company_id.certificate_file, self.company_id.certificate_password
        )
        output = BytesIO()
        zipfile = ZipFile(output, mode="w")
        zipfile_content = BytesIO()
        zipfile_content.write(b64decode(self.xml_file))
        zipfile.writestr(self.xml_filename, zipfile_content.getvalue())
        zipfile_content = BytesIO()
        zipfile_content.write(b64decode(self.ar_xml_file))
        zipfile.writestr(self.ar_xml_filename, zipfile_content.getvalue())
        zipfile.close()
        xml_soap_values["fileName"] = self.zipped_filename.replace(".zip", "")
        xml_soap_values["contentFile"] = b64encode(output.getvalue()).decode("uft-8")

        return xml_soap_values

    def action_SendBillAttachmentAsync(self):
        b = "http://schemas.datacontract.org/2004/07/UploadDocumentResponse"
        wsdl = DIAN_URL["wsdl-hab"]

        if self.company_id.profile_execution_id == "1":
            wsdl = DIAN_URL["wsdl"]

        SendBillAttachmentAsync_values = self._get_SendBillAttachmentAsync_values()
        SendBillAttachmentAsync_values["To"] = wsdl.replace("?wsdl", "")
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(
                SendBillAttachmentAsync_values, "SendBillAttachmentAsync"
            ),
            SendBillAttachmentAsync_values["Id"],
            self.company_id.certificate_file,
            self.company_id.certificate_password,
        )
        timeout = 10

        for attempt in range(3):
            try:
                response = post(
                    wsdl,
                    headers={"content-type": "application/soap+xml;charset=utf-8"},
                    data=etree.tostring(xml_soap_with_signature),
                    timeout=timeout,
                )

                if response.status_code == 200:
                    self.write({"state": "sent"})
                    root = etree.fromstring(response.text.encode("utf-8"))

                    for element in root.iter("{%s}ZipKey" % b):
                        self.write({"zip_key": element.text})
                        self.action_GetStatusZip()
                elif response.status_code in (403, 500, 503, 507, 508):
                    self.env["account.invoice.dian.document.line"].create(
                        {
                            "dian_document_id": self.id,
                            "send_async_status_code": response.status_code,
                            "send_async_reason": response.reason,
                            "send_async_response": response.text,
                        }
                    )
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

        return True
