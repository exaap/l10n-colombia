# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0).

import hashlib
from os import path
from uuid import uuid4
from base64 import b64encode, b64decode
from io import BytesIO
from datetime import datetime, timedelta
import OpenSSL.crypto as crypto
from lxml import etree
from jinja2 import Environment, FileSystemLoader
from pgxades import XAdESContext, PolicyId, template
import xmlsig
from odoo import _
from odoo.exceptions import ValidationError


def get_SoftwareSecurityCode(IdSoftware, Pin, NroDocumentos):
    uncoded_value = IdSoftware + " + " + Pin + " + " + NroDocumentos
    software_security_code = IdSoftware + Pin + NroDocumentos
    software_security_code = hashlib.sha384(software_security_code.encode("utf-8"))

    return {
        "SoftwareSecurityCodeUncoded": uncoded_value,
        "SoftwareSecurityCode": software_security_code.hexdigest(),
    }


def get_UUID(
    NumFac,
    FecFac,
    HorFac,
    ValFac,
    CodImp1,
    ValImp1,
    CodImp2,
    ValImp2,
    CodImp3,
    ValImp3,
    ValTot,
    NitOFE,
    NumAdq,
    ClTec,
    SoftwarePIN,
    TipoAmbie,
):
    # CUFE = SHA-384(NumFac + FecFac + HorFac + ValFac + CodImp1 + ValImp1 + CodImp2 +
    # ValImp2 + CodImp3 + ValImp3 + ValTot + NitOFE + NumAdq + ClTec + TipoAmbie)
    # CUDE = SHA-384(NumFac + FecFac + HorFac + ValFac + CodImp1 + ValImp1 + CodImp2 +
    # ValImp2 + CodImp3 + ValImp3 + ValTot + NitOFE + NumAdq + Software-PIN + TipoAmbie)
    # CUDS = SHA-384(NumFac + FecFac + HorFac + ValDS + CodImp + ValImp + ValTot +
    # NitOFE + NumAdq + SoftwarePIN + TipoAmbie)
    uncoded_OtrosImp = ""
    OtrosImp = ""

    if CodImp2:
        uncoded_OtrosImp = (
            CodImp2 + " + " + ValImp2 + " + " + CodImp3 + " + " + ValImp3 + " + "
        )
        OtrosImp = CodImp2 + ValImp2 + CodImp3 + ValImp3

    uncoded_value = (
        NumFac
        + " + "
        + FecFac
        + " + "
        + HorFac
        + " + "
        + ValFac
        + " + "
        + CodImp1
        + " + "
        + ValImp1
        + " + "
        + uncoded_OtrosImp
        + ValTot
        + " + "
        + NitOFE
        + " + "
        + NumAdq
        + " + "
        + (ClTec if ClTec else SoftwarePIN)
        + " + "
        + TipoAmbie
    )
    value = (
        NumFac
        + FecFac
        + HorFac
        + ValFac
        + CodImp1
        + ValImp1
        + OtrosImp
        + ValTot
        + NitOFE
        + NumAdq
        + (ClTec or SoftwarePIN)
        + TipoAmbie
    )
    value = hashlib.sha384(value.encode("utf-8"))

    return {"CUFE/CUDE/CUDSUncoded": uncoded_value, "CUFE/CUDE/CUDS": value.hexdigest()}


def get_ApplicationResponseUUID(
    Num_DE,
    Fec_Emi,
    Hor_Emi,
    NitFE,
    DocAdq,
    ResponseCode,
    ID,
    DocumentTypeCode,
    SoftwarePIN,
):
    # CUDE = SHA-384(Num_DE + Fec_Emi + Hor_Emi + NitFE + DocAdq + ResponseCode + ID +
    # DocumentTypeCode + Software-PIN)
    uncoded_value = (
        Num_DE
        + " + "
        + Fec_Emi
        + " + "
        + Hor_Emi
        + " + "
        + NitFE
        + " + "
        + DocAdq
        + " + "
        + ResponseCode
        + " + "
        + ID
        + " + "
        + DocumentTypeCode
        + " + "
        + SoftwarePIN
    )
    value = (
        Num_DE
        + Fec_Emi
        + Hor_Emi
        + NitFE
        + DocAdq
        + ResponseCode
        + ID
        + DocumentTypeCode
        + SoftwarePIN
    )
    value = hashlib.sha384(value.encode("utf-8"))

    return {"CUDEUncoded": uncoded_value, "CUDE": value.hexdigest()}


# https://stackoverflow.com/questions/38432809/dynamic-xml-template-generation-using-get-template-jinja2
def get_template_xml(values, template_name):
    base_path = path.dirname(path.dirname(__file__))
    env = Environment(loader=FileSystemLoader(path.join(base_path, "templates")))
    template_xml = env.get_template("{}.xml".format(template_name))
    xml = template_xml.render(values)

    return xml.replace("&", "&amp;").encode("utf-8")


def get_pkcs12(certificate_file, certificate_password):
    msg = _(
        "The certificate password or certificate file is not valid.\n\n" "Exception: %s"
    )

    try:
        return crypto.load_pkcs12(b64decode(certificate_file), certificate_password)
    except Exception as e:
        raise ValidationError(msg % e)


# https://www.decalage.info/en/python/lxml-c14n
def get_xml_with_c14n(xml):
    if not isinstance(xml, etree._Element):
        xml = etree.fromstring(xml.encode("utf-8"))

    out = BytesIO()
    xml.getroottree().write_c14n(out)
    value = b64encode(out.getvalue()).decode("utf-8")
    out.close()

    return value


# https://github.com/etobella/python-xades
def get_xml_with_signature(
    xml_without_signature,
    signature_policy_url,
    signature_policy_file,
    signature_policy_description,
    certificate_file,
    certificate_password,
):
    # https://lxml.de/tutorial.html
    # root = etree.fromstring(response.content)
    # root = etree.tostring(root, encoding='utf-8')
    # parser = etree.XMLParser(encoding='utf-8', remove_blank_text=True)
    ds = "http://www.w3.org/2000/09/xmldsig#"
    ext = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
    parser = etree.XMLParser(remove_comments=True, remove_blank_text=True)
    root = etree.fromstring(xml_without_signature, parser=parser)
    signature_id = "xmldsig-{}".format(uuid4())
    signature = xmlsig.template.create(
        xmlsig.constants.TransformInclC14N,
        xmlsig.constants.TransformRsaSha512,
        signature_id,
    )

    # Complememto para añadir atributo faltante
    for element in root.iter("{%s}SignatureValue" % ds):
        element.attrib["Id"] = signature_id + "-sigvalue"

    ref = xmlsig.template.add_reference(
        signature, xmlsig.constants.TransformSha512, uri="", name=signature_id + "-ref0"
    )
    xmlsig.template.add_transform(ref, xmlsig.constants.TransformEnveloped)
    sp = xmlsig.template.add_reference(
        signature,
        xmlsig.constants.TransformSha512,
        uri="#" + signature_id + "-signedprops",
        uri_type="http://uri.etsi.org/01903#SignedProperties",
    )
    xmlsig.template.add_transform(sp, xmlsig.constants.TransformInclC14N)
    xmlsig.template.add_reference(
        signature, xmlsig.constants.TransformSha512, uri="#" + signature_id + "-keyinfo"
    )
    ki = xmlsig.template.ensure_key_info(signature, name=signature_id + "-keyinfo")
    data = xmlsig.template.add_x509_data(ki)
    xmlsig.template.x509_data_add_certificate(data)
    xmlsig.template.x509_data_add_subject_name(data)
    serial = xmlsig.template.x509_data_add_issuer_serial(data)
    xmlsig.template.x509_issuer_serial_add_issuer_name(serial)
    xmlsig.template.x509_issuer_serial_add_serial_number(serial)
    xmlsig.template.add_key_value(ki)
    qualifying = template.create_qualifying_properties(signature)
    props = template.create_signed_properties(
        qualifying, name=signature_id + "-signedprops"
    )
    template.add_claimed_role(props, "supplier")
    policy = PolicyId()
    policy.id = signature_policy_url
    policy.name = signature_policy_description
    policy.remote = b64decode(signature_policy_file)
    policy.hash_method = xmlsig.constants.TransformSha512
    ctx = XAdESContext(policy)
    ctx.load_pkcs12(get_pkcs12(certificate_file, certificate_password))
    root.append(signature)
    ctx.sign(signature)
    ctx.verify(signature)
    root.remove(signature)
    position = 0

    for element in root.iter("{%s}ExtensionContent" % ext):
        if position == 1:
            element.append(signature)

        position += 1

    return get_xml_with_c14n(root)


def get_xml_soap_values(certificate_file, certificate_password):
    Created = datetime.utcnow()
    Expires = Created + timedelta(seconds=60000)
    Created = Created.strftime("%Y-%m-%dT%H:%M:%S.001Z")
    Expires = Expires.strftime("%Y-%m-%dT%H:%M:%S.001Z")
    # https://github.com/mit-dig/idm/blob/master/idm_query_functions.py#L151
    pkcs12 = get_pkcs12(certificate_file, certificate_password)
    cert = pkcs12.get_certificate()
    der = b64encode(crypto.dump_certificate(crypto.FILETYPE_ASN1, cert)).decode("utf-8")

    return {
        "Created": Created,
        "Expires": Expires,
        "Id": uuid4(),
        "BinarySecurityToken": der,
    }


def get_xml_soap_with_signature(
    xml_soap_without_signature, Id, certificate_file, certificate_password
):
    wsse = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    wsu = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    X509v3 = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"
    parser = etree.XMLParser(remove_comments=True, remove_blank_text=True)
    root = etree.fromstring(xml_soap_without_signature, parser=parser)
    signature_id = "{}".format(Id)
    signature = xmlsig.template.create(
        xmlsig.constants.TransformExclC14N,
        xmlsig.constants.TransformRsaSha256,  # solo me ha funcionado con esta
        "SIG-" + signature_id,
    )
    ref = xmlsig.template.add_reference(
        signature, xmlsig.constants.TransformSha256, uri="#id-" + signature_id
    )
    xmlsig.template.add_transform(ref, xmlsig.constants.TransformExclC14N)
    ki = xmlsig.template.ensure_key_info(signature, name="KI-" + signature_id)
    ctx = xmlsig.SignatureContext()
    ctx.load_pkcs12(get_pkcs12(certificate_file, certificate_password))

    for element in root.iter("{%s}Security" % wsse):
        element.append(signature)

    ki_str = etree.SubElement(ki, "{%s}SecurityTokenReference" % wsse)
    ki_str.attrib["{%s}Id" % wsu] = "STR-" + signature_id
    ki_str_reference = etree.SubElement(ki_str, "{%s}Reference" % wsse)
    ki_str_reference.attrib["URI"] = "#X509-" + signature_id
    ki_str_reference.attrib["ValueType"] = X509v3
    ctx.sign(signature)
    ctx.verify(signature)

    return root
