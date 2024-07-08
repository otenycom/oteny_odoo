# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
from markupsafe import escape


class RiverFlowWorkflowTransition(models.Model):
    _name = 'riverflow.workflow.transition'
    _description = 'Workflow state transition'
    _order = "from_state_id,sequence,name,id"
    _rec_name = 'complete_name'

    name = fields.Char('Transition name', required=True)
    description = fields.Text('Description', required=False)
    sequence = fields.Integer(default=10)
    icon = fields.Char(
        'Icon', help="Font awesome icon e.g. fa-tasks")
    icon_name_html = fields.Html(
        'Name', compute='_compute_icon_name_html', store=True, help="Combination of Icon and name")
    active = fields.Boolean('Active', default=True)
    from_state_id = fields.Many2one(
        'riverflow.workflow.state', 'From', help='Leave blank to define a start-transition',
        copy=True, index=True, required=False)
    to_state_id = fields.Many2one(
        'riverflow.workflow.state', 'To', copy=True, index=True, required=True)
    workflow_id = fields.Many2one(
        'riverflow.workflow', string='Workflow', help='Derived from the to-state, since the from-state is optional', compute='_compute_workflow_id', store=True)
    action_id = fields.Many2one(
        'riverflow.workflow.transition.action',
        'Action', copy=True)
    action_context = fields.Text("Action context",
                                 help='Configuration values for the action screen', copy=True)
    complete_name = fields.Char(
        'Complete Name', compute='_compute_complete_name', store=True, index='trigram')

    # email_template_id = fields.Many2one('mail.template', 'Email Template', copy=True, domain=[
    #                                     ('model', '=', 'riverflow.workflow')])
    # report_id = fields.Many2one('ir.actions.report', 'Report', copy=True, domain=[

    @api.depends('to_state_id.workflow_id')
    def _compute_workflow_id(self):
        for transition in self:
            transition.workflow_id = transition.to_state_id.workflow_id

    @api.depends('name', 'from_state_id', 'from_state_id')
    def _compute_complete_name(self):
        for transition in self:
            fromState = transition.from_state_id.name if transition.from_state_id else 'Start'
            transition.complete_name = f"{fromState} -> ({transition.name}) -> {transition.to_state_id.name}"

    @api.depends('icon', "name", "action_id.icon")
    def _compute_icon_name_html(self):
        for record in self:
            icon = record.icon or record.action_id.icon
            if icon:
                record.icon_name_html = f'<span><span class="fa {escape(icon)}"></span>&nbsp;{escape(record.name)}</span>'
            else:
                record.icon_name_html = escape(record.name)
