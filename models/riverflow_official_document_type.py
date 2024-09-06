from odoo import models, fields, api


class OfficialDocumentType(models.Model):
    _name = "riverflow.official.document.type"
    _description = "Official Document Type"

    name = fields.Char(string="Name", required=True, index=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)

    _sql_constraints = [
        ("code_unique", "unique(code)", "The document type code must be unique")
    ]

    # Add a brief comment explaining the purpose of the sequence field
    _order = "sequence, name"  # Order records by sequence, then by name
