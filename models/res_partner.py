from odoo import fields, models, api

from .riverflow_team import RiverflowTeam


class Contact(models.Model):
    _inherit = "res.partner"

    team_ids: RiverflowTeam = fields.One2many("riverflow.team", "partner_id", string="Teams")

    is_user = fields.Boolean(compute="_compute_is_user", store=True)
    is_team = fields.Boolean(compute="_compute_is_team", store=True)

    @api.depends("user_ids")
    def _compute_is_user(self):
        for record in self:
            record.is_user = len(record.user_ids) > 0

    @api.depends("team_ids")
    def _compute_is_team(self):
        for record in self:
            record.is_team = len(record.team_ids) > 0
