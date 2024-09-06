from odoo import models, api


class Document(models.Model):
    _name = "documents.document"
    _inherit = "documents.document"

    def write(self, vals):
        for record in self:
            previous_res_model = record.res_model
            previous_res_id = record.res_id

            # Find the previous target document
            previous_target = False
            if previous_res_model and previous_res_id:
                previous_target = (
                    self.env[previous_res_model].browse(previous_res_id).exists()
                )

            result = super(Document, self).write(vals)

            # Clear document_id on the previous target if res_model or res_id changed
            if "res_model" in vals or "res_id" in vals:
                if previous_target and hasattr(previous_target, "document_id"):
                    previous_target.write({"document_id": False})

            # Set document_id on the new target
            if record.res_model and record.res_id:
                new_target = self.env[record.res_model].browse(record.res_id).exists()
                if new_target and hasattr(new_target, "document_id"):
                    new_target.write({"document_id": record.id})

        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super(Document, self).create(vals_list)
        for record in records:
            if record.res_model and record.res_id:
                target = self.env[record.res_model].browse(record.res_id).exists()
                if target and hasattr(target, "document_id"):
                    target.write({"document_id": record.id})
        return records
