# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class RiverFlowWorkflowState(models.Model):
    _name = 'riverflow.workflow.state'
    _description = 'Workflow state'
    _order = "workflow_id,sequence,name,id"

    name = fields.Char('State name', required=True)
    description = fields.Text('Description', required=False)
    active = fields.Boolean('Active', default=True)
    workflow_id = fields.Many2one(
        'riverflow.workflow', 'Workflow', copy=True, index=True, required=True)
    sequence = fields.Integer(default=10)
    isEndState = fields.Boolean('Is End State', default=False)

    from_transition_ids = fields.One2many(
        'riverflow.workflow.transition', 'from_state_id', string='From-transitions', help='Transitions from this state')

    complete_name = fields.Char(
        'Complete Name', compute='_compute_complete_name', store=True, index='trigram')

    @api.depends('name', 'workflow_id')
    def _compute_complete_name(self):
        for state in self:
            state.complete_name = f"{state.name} | {state.workflow_id.name}"
