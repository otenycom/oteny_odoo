# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class RiverFlowWorkflowState(models.Model):
    _name = 'riverflow.workflow'
    _description = 'Workflow'
    _order = "name"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Workflow name', index='trigram', required=True)
    description = fields.Text('Description', required=False)
    active = fields.Boolean('Active', default=True)

    workflow_state_ids = fields.One2many(
        'riverflow.workflow.state', 'workflow_id', string='Workflow states')

    workflow_start_transition_ids = fields.One2many(
        'riverflow.workflow.transition', 'workflow_id', domain=[('from_state_id', '=', False)], string='Start transitions')

    _sql_constraints = [('name_uniq', 'unique (name)',
                         "Workflow name already exists!")]
