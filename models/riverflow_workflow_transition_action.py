# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
from markupsafe import escape


class RiverFlowWorkflowTransitionAction(models.Model):
    _name = 'riverflow.workflow.transition.action'
    _description = 'Workflow transition action'
    _order = "name"

    name = fields.Char('Action name', required=True)
    icon_name_html = fields.Html(
        'Name', compute='_compute_icon_name_html', help="Combination of Icon and name", store=True)
    description = fields.Text('Description', required=True)
    active = fields.Boolean('Active', default=True)
    icon = fields.Char(
        'Icon', help="Font awesome icon e.g. fa-tasks. If blank, the relation action's icon will be used.")
    odoo_view = fields.Text(
        'Odoo View', help="Odoo wizard form-view")

    _sql_constraints = [('name_uniq', 'unique (name)',
                         "Workflow name already exists!")]

    @api.depends('icon', "name")
    def _compute_icon_name_html(self):
        for record in self:
            if record.icon:
                record.icon_name_html = f'<span><span class="fa {escape(record.icon)}"></span>&nbsp;{escape(record.name)}</span>'
            else:
                record.icon_name_html = escape(record.name)
