# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class RiverFlowWorkflowState(models.Model):
    _name = 'riverflow.workflow.transition.action'
    _description = 'Workflow transition action'
    _order = "name"

    name = fields.Char('Name', required=True)
    description = fields.Text('Description', required=True)
    icon = fields.Char(
        'Icon', help="Font awesome icon e.g. fa-tasks")
    odoo_action = fields.Text(
        'Odoo action', help="An Odoo-action command, for example to open a screen")

    _sql_constraints = [('name_uniq', 'unique (name)',
                         "Workflow name already exists!")]
