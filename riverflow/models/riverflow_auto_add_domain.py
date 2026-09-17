from odoo import api, fields, models


class AutoAddDomain(models.Model):
    _name = "riverflow.auto.add.domain"
    _description = "Auto Add Domain"
    _order = "applies_to_model,name"

    name = fields.Char(required=True, index=True)
    description = fields.Text(help="Human readable description of this domain condition.")
    applies_to_model_id = fields.Many2one(
        "ir.model",
        string="Applies to",
        required=True,
        ondelete="cascade",
    )
    domain = fields.Text(
        required=True,
        default="[]",
        help="Domain expression to evaluate.",
    )
    applies_to_model = fields.Char(
        string="Technical Model Name",
        related="applies_to_model_id.model",
        store=True,
        readonly=True,
    )
