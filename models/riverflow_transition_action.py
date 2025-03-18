from odoo import models, fields, api
from markupsafe import escape


class RiverflowTransitionAction(models.Model):
    _name = "riverflow.transition.action"
    _description = "Workflow transition action"
    _order = "model,name"

    name = fields.Char("Action name", required=True)
    icon_name_html = fields.Html(
        "Name",
        compute="_compute_icon_name_html",
        help="Combination of Icon and name",
        store=True,
    )
    description = fields.Text("Description", required=True)
    active = fields.Boolean("Active", default=True)
    icon = fields.Char(
        "Icon",
        help="Font awesome icon e.g. fa-tasks. If blank, the relation action's icon will be used.",
    )

    model_id = fields.Many2one("ir.model", "Applies to")
    model = fields.Char("Related Model", related="model_id.model", index=True, store=True, readonly=True)

    odoo_view = fields.Text("Odoo View", help="Odoo wizard form-view")

    _sql_constraints = [("name_uniq", "unique (name)", "Workflow name already exists!")]

    @api.depends("icon", "name")
    def _compute_icon_name_html(self):
        for record in self:
            if record.icon:
                record.icon_name_html = (
                    f'<span><span class="fa {escape(record.icon)}"></span>&nbsp;{escape(record.name)}</span>'
                )
            else:
                record.icon_name_html = escape(record.name)
