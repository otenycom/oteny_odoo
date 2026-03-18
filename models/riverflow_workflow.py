from odoo import models, fields, api
from markupsafe import escape


class RiverflowWorkflow(models.Model):
    _name = "riverflow.workflow"
    _description = "Workflow"
    _order = "model,name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"

    name = fields.Char("Workflow name", index="trigram", required=True)
    description = fields.Text("Description", required=False)
    icon = fields.Char("Workflow icon", help="Font awesome icon e.g. fa-tasks")
    icon_name_html = fields.Html(
        "Name",
        compute="_compute_icon_name_html",
        help="Combination of Icon and name",
        store=True,
    )
    active = fields.Boolean("Active", default=True)

    state_ids = fields.One2many("riverflow.state", "workflow_id", string="Workflow states")

    auto_complete_state_id = fields.Many2one(
        "riverflow.state",
        string="Auto-Complete State",
        domain="[('workflow_id', '=', id), ('is_end_state', '=', True)]",
        help="End state for services auto-completed when a credential plan item "
        "becomes 'issued'. Set to 'Not Needed' or similar end state.",
    )

    workflow_start_transition_ids = fields.One2many(
        "riverflow.transition",
        "workflow_id",
        domain=[("from_state_id", "=", False)],
        string="Start transitions",
    )

    model_id = fields.Many2one("ir.model", "Applies to", required=True, ondelete="cascade")
    model = fields.Char("Related Model", related="model_id.model", index=True, store=True, readonly=True)
    friendly_model_name = fields.Char(
        "Friendly Model Name", compute="_compute_friendly_model_name", store=True
    )

    display_name = fields.Char("Display Name", compute="_compute_display_name", store=True, index=True)

    is_supply_order = fields.Boolean(
        "Is Supply Order",
        help="If checked, this workflow is for a supply order, e.g a Taxi Order",
        required=False,
        tracking=True,
    )
    has_supply_quantity = fields.Boolean(
        "Has Supply Quantity",
        help="If checked, this workflow has a supply quantity field",
        tracking=True,
        default=False,
    )
    has_supply_unit_price = fields.Boolean(
        "Has Cost Price",
        help="If checked, this workflow has a cost price field",
        tracking=True,
        default=False,
    )
    has_supplier = fields.Boolean(
        "Has Supplier",
        help="If checked, this workflow has a supplier field. If not, it is a self arranged service such as a flight booking.",
        tracking=True,
        default=False,
    )
    has_legs = fields.Boolean(
        "Has Legs",
        help="If checked, this workflow has route-legs for ground transport services.",
        tracking=True,
        default=False,
    )

    # Upgrade to Odoo 19 constraint style
    _name_uniq = models.Constraint(
        "unique (name)",
        "Workflow name already exists!",
    )

    @api.depends("icon", "name")
    def _compute_icon_name_html(self):
        for record in self:
            if record.icon:
                record.icon_name_html = (
                    f'<span><span class="fa {escape(record.icon)}"></span>&nbsp;{escape(record.name)}</span>'
                )
            else:
                record.icon_name_html = escape(record.name)

    @api.depends("model_id")
    def _compute_friendly_model_name(self):
        for record in self:
            record.friendly_model_name = record.model_id.name

    @api.depends("name", "friendly_model_name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.friendly_model_name})"

    def workflow_add_start_transition(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Add Start Transition to: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.transition",
            "context": {"default_workflow_id": self.id, "is_start_transition": True},
            "target": "current",
        }

    def workflow_add_state(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Add Workflow State to: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.state",
            "context": {"default_workflow_id": self.id},
            "target": "current",
        }
