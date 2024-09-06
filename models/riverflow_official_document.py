from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


class OfficialDocument(models.Model):
    _name = "riverflow.official.document"
    _description = "Official Document"
    _inherit = ["mail.thread"]

    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,
    )

    document_id = fields.Many2one("documents.document", string="Document")
    document_type_id = fields.Many2one(
        "riverflow.official.document.type", string="Document Type", required=True
    )
    number = fields.Char(string="Number")
    issuing_country_id = fields.Many2one(
        "res.country", string="Issuing Country", required=False
    )
    issue_date = fields.Date(string="Issue Date")
    expiry_date = fields.Date(string="Expiry Date")

    # the holder of the official document (ship, contact/operator, employee, etc)
    holder_id = fields.Integer(string="Holder ID", required=False)
    holder_model = fields.Char(
        string="Holder Model",
    )
    holder_name = fields.Char(
        string="Holder",
        compute="_compute_holder_name",
        store=True,
        index="trigram",
    )
    holder_ref = fields.Reference(
        string="Holder Reference",
        selection="_selection_target_model",
        compute="_compute_holder_ref",
        inverse="_set_holder_ref",
    )

    @api.depends("document_type_id", "number", "holder_name", "issue_date")
    def _compute_display_name(self):
        for document in self:
            display_name_parts = []
            if document.document_type_id.name:
                display_name_parts.append(document.document_type_id.name)
            if document.holder_name:
                display_name_parts.append(f"({document.holder_name})")
            if document.issue_date:
                display_name_parts.append(document.issue_date.strftime("%Y-%m-%d"))
            if document.number:
                display_name_parts.append(document.number)

            document.display_name = " - ".join(filter(None, display_name_parts))

    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    @api.depends("holder_model", "holder_id")
    def _compute_holder_ref(self):
        for offidoc in self:
            if not offidoc.holder_model or not offidoc.holder_id:
                offidoc.holder_ref = False
            else:
                offidoc.holder_ref = "%s,%s" % (
                    offidoc.holder_model,
                    offidoc.holder_id,
                )

    def _set_holder_ref(self):
        for offidoc in self:
            if offidoc.holder_ref:
                offidoc.holder_id = offidoc.holder_ref.id
                offidoc.holder_model = offidoc.holder_ref._name
            else:
                offidoc.holder_id = False
                offidoc.holder_model = False

    @api.depends("holder_model", "holder_id")
    def _compute_holder_name(self):
        for offidoc in self:
            if not offidoc.holder_id or not offidoc.holder_model:
                offidoc.holder_name = False
                continue
            if offidoc.holder_model not in self.env:
                # Skip if the container model is not yet loaded in the environment
                #  (during upgrades of the module, when the container is a module dependent on riverflow)
                continue
            record = self.env[offidoc.holder_model].sudo().browse(offidoc.holder_id)
            if not record.exists():
                offidoc.holder_name = False
                continue
            name = record.display_name
            offidoc.holder_name = (
                name if name else f"{offidoc.holder_model}/{offidoc.holder_id}"
            )

    def _get_document_folder(self):
        return False

    def _get_documents_domain(self):
        self.ensure_one()
        if self.document_id:
            domain = [("id", "=", self.document_id.id)]
        else:
            domain = []
        return domain

    def on_click_open_document(self):
        self.ensure_one()
        if not self.document_id:
            pass

        action = self._get_show_documents_action()
        return action

    def _get_show_documents_action(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "documents.document_action"
        )
        action["context"] = {"default_res_model": self._name, "default_res_id": self.id}
        action["domain"] = self._get_documents_domain()
        return action

    def write(self, vals):
        if not "document_id" in vals:
            return super(OfficialDocument, self).write(vals)

        for record in self:
            previous_document_id = record.document_id
            result = super(OfficialDocument, self).write(vals)
            if record.document_id != previous_document_id:
                if previous_document_id:
                    previous_document_id.write(
                        {
                            "res_model": False,
                            "res_id": False,
                        }
                    )
                if record.document_id:
                    record.document_id.write(
                        {
                            "res_model": self._name,
                            "res_id": record.id,
                        }
                    )
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super(OfficialDocument, self).create(vals_list)
        for record in records:
            if record.document_id:
                record.document_id.write(
                    {
                        "res_model": self._name,
                        "res_id": record.id,
                    }
                )
        return records
