from odoo import fields, models, api


class Contact(models.Model):
    _inherit = "res.partner"

    team_ids = fields.One2many("riverflow.team", "partner_id", string="Teams")

    is_user = fields.Boolean(compute="_compute_is_user", store=True)
    is_riverflow_team = fields.Boolean(compute="_compute_is_riverflow_team", store=True)
    riverflow_team_id = fields.Many2one(
        "riverflow.team", string="Team", compute="_compute_riverflow_team_id", store=True
    )

    @api.depends("user_ids")
    def _compute_is_user(self):
        for record in self:
            record.is_user = len(record.user_ids.filtered(lambda u: u.has_group("base.group_user"))) > 0

    @api.depends("team_ids")
    def _compute_is_riverflow_team(self):
        for record in self:
            record.is_riverflow_team = len(record.team_ids) > 0

    @api.depends("team_ids")
    def _compute_riverflow_team_id(self):
        for record in self:
            record.riverflow_team_id = record.team_ids[0] if record.team_ids else False
