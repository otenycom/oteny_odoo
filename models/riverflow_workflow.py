# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
from markupsafe import escape


class RiverFlowWorkflowState(models.Model):
    _name = 'riverflow.workflow'
    _description = 'Workflow'
    _order = "name"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Workflow name', index='trigram', required=True)
    description = fields.Text('Description', required=False)
    icon = fields.Char('Icon', help="Font awesome icon e.g. fa-tasks")
    icon_name_html = fields.Html(
        'Name', compute='_compute_icon_name_html', help="Combination of Icon and name", store=True)

    active = fields.Boolean('Active', default=True)

    workflow_state_ids = fields.One2many(
        'riverflow.workflow.state', 'workflow_id', string='Workflow states')

    workflow_start_transition_ids = fields.One2many(
        'riverflow.workflow.transition', 'workflow_id', domain=[('from_state_id', '=', False)], string='Start transitions')

    _sql_constraints = [('name_uniq', 'unique (name)',
                         "Workflow name already exists!")]

    @api.depends('icon', "name")
    def _compute_icon_name_html(self):
        for record in self:
            if record.icon:
                record.icon_name_html = f'<span><span class="fa {escape(record.icon)}"></span>&nbsp;{escape(record.name)}</span>'
            else:
                record.icon_name_html = escape(record.name)
