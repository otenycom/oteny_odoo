from odoo import fields, models


class RiverflowServiceTag(models.Model):
    _name = "riverflow.service.tag"
    _description = "Service Tag"

    name = fields.Char("Tag Name", required=True, translate=True)
    color = fields.Integer("Color")

    _sql_constraints = [("name_uniq", "unique (name)", "Tag name already exists!")]
