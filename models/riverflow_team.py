from odoo import fields, models, api


class RiverflowTeam(models.Model):
    _name = "riverflow.team"
    # mail.thread is needed for the change tracking to work
    _inherit = ["mail.thread", "avatar.mixin"]
    _description = "Team"
    _order = "name"

    name = fields.Char(
        "Team Name",
        store=True,
        required=True,
        tracking=True,
    )
    active = fields.Boolean("Active", tracking=True, default=True)
    color = fields.Char("Color", default="#FFA500")  # Fresh orange color
    discuss_channel_id = fields.Many2one(
        "discuss.channel",
        "Discuss Channel",
        required=False,
        help="This channel is used to alert the team of new unreviewed external messages.",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        default=lambda self: self.env.company,
        required=True,
        help="The company that this team is associated with.",
    )
