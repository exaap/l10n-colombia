# Copyright 2024 Joan Marín <Github@JoanMarin>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3

from base64 import b64encode
from odoo import models, api
from odoo.tools import pycompat


class MailTemplate(models.Model):
    _inherit = "mail.template"

    @api.multi
    def generate_email(self, res_ids, fields=None):
        res = super(MailTemplate, self).generate_email(res_ids, fields)
        multi_mode = True

        if isinstance(res_ids, pycompat.integer_types):
            res_ids = [res_ids]
            multi_mode = False

        if self.model != "account.invoice.dian.document":
            return res

        for document_id in self.env[self.model].browse(res_ids):
            attachment_ids = self.env["ir.attachment"].create(
                {
                    "name": document_id.ad_zipped_filename,
                    "datas_fname": document_id.ad_zipped_filename,
                    "datas": document_id.ad_zipped_file,
                }
            )
            res["attachment_ids"] = attachment_ids.ids

        return res
