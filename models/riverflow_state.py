# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class RiverflowWorkflowState(models.Model):
    _name = "riverflow.state"
    _description = "Workflow state"
    _order = "workflow_id,sequence,name,id"
    _rec_name = "display_name"

    name = fields.Char("State name", required=True)
    description = fields.Text("Description", required=False)
    active = fields.Boolean("Active", default=True)
    workflow_id = fields.Many2one(
        "riverflow.workflow", "Workflow", copy=True, index=True, required=True
    )
    sequence = fields.Integer(default=10)
    is_end_state = fields.Boolean("Is End State", default=False)
    is_cancelled_state = fields.Boolean("Is Cancelled State", default=False)

    from_transition_ids = fields.One2many(
        "riverflow.transition",
        "from_state_id",
        string="From-transitions",
        help="Transitions from this state",
    )

    display_name = fields.Char(
        "Display Name", compute="_compute_display_name", store=True, index="trigram"
    )

    @api.depends("name", "workflow_id.name")
    def _compute_display_name(self):
        for state in self:
            state.display_name = (
                f"{state.workflow_id.display_name} | {state.name}"  # fmt: off
            )

    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     args = args or []
    #     domain = []
    #     if name:
    #         domain = [('display_name', operator, name)]
    #     return self.search(domain + args, limit=limit).ids

    def workflow_add_from_transition(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Add Transition from: " + self.name,
            "view_mode": "form",
            "res_model": "riverflow.transition",
            "context": {
                "default_workflow_id": self.workflow_id.id,
                "default_from_state_id": self.id,
                "is_start_transition": False,
            },
            "target": "current",
        }
