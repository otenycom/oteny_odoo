from odoo import fields, models, api


class RiverflowTeam(models.Model):
    _name = "riverflow.team"
    _inherits = {"res.partner": "partner_id"}
    _description = "Team"
    _order = "name"
    _inherit = ["mail.thread", "avatar.mixin"]

    # Link to the partner record that stores the team's contact information
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
        auto_join=True,
        string="Related Partner",
        help="Partner record storing the team's contact information",
    )
    name = fields.Char(related="partner_id.name", inherited=True, readonly=False)

    # Team-specific fields
    discuss_channel_id = fields.Many2one(
        "discuss.channel",
        "Discuss Channel",
        required=False,
        help="This channel is used to alert the team of new unreviewed external messages.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure partner is created as a company"""
        for vals in vals_list:
            vals["is_company"] = True
        return super().create(vals_list)

    def action_related_contact(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "view_mode": "form",
            "target": "main",
        }
