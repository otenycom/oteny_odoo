from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    restrict_email_recipients_to = fields.Char(
        string="Restrict Email Recipients To",
        config_parameter="riverflow.restrict_email_recipients_to",
        help="Comma-separated list of allowed email domains (e.g., example.com,example.org)",
    )
