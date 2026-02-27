from odoo import api, fields, models


class IrFilters(models.Model):
    _inherit = "ir.filters"

    # Shortcut fields: promote a saved Favorite to a quick-access button
    # in the view shortcuts banner. Set shortcut_sequence > 0 to enable.
    shortcut_sequence = fields.Integer(
        default=0,
        help="When greater than 0, this filter appears as a shortcut button "
        "above list/calendar views that use the shortcut js_class. "
        "Lower values appear first.",
    )
    shortcut_view_type = fields.Selection(
        [("list", "List"), ("calendar", "Calendar")],
        string="Shortcut View",
        help="Preferred view type when clicking the shortcut button. "
        "Leave empty to stay on the current view.",
    )
    shortcut_icon = fields.Char(
        string="Shortcut Icon",
        help="Font Awesome icon class for the shortcut button, e.g. fa-clock-o",
    )

    @api.model
    def get_shortcuts(self, res_model, action_id=None):
        """Return filters configured as shortcut buttons for the current user.

        Reuses the built-in ir.filters visibility rules: a filter is visible
        when user_ids is empty (shared with everyone) or contains the
        current user.
        """
        action_domain = self._get_action_domain(action_id)
        domain = action_domain + [
            ("model_id", "=", res_model),
            ("shortcut_sequence", ">", 0),
            ("user_ids", "in", [self.env.uid, False]),
        ]
        return (
            self.search(domain, order="shortcut_sequence, name")
            .read(["name", "shortcut_sequence", "shortcut_view_type", "shortcut_icon"])
        )
