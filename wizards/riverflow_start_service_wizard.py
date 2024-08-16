from odoo import models, fields


class ServiceNewWizard(models.TransientModel):
    _name = "riverflow.start.service"
    _inherit = "riverflow.start.wizard"
    _description = "Service Start Transition selection Wizard"

    _workflow_model = "riverflow.service"

    # captures default subject for the service from the context, in case its a start-transition
    res_id = fields.Integer(string="Service's Subject", required=False)
    res_model = fields.Char(
        string="Service's Subject Model Name",
    )
