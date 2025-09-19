from odoo import fields, models


class RiverflowServiceTag(models.Model):
    _name = "riverflow.service.tag"
    _description = "Service Tag"
    _order = "name"

    name = fields.Char("Tag Name", required=True, translate=True)
    color = fields.Integer("Color")

    # Upgrade to Odoo 19 constraint style
    _name_uniq = models.Constraint(
        "unique (name)",
        "Tag name already exists!",
    )
