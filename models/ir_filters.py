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
        selection="_shortcut_view_type_selection",
        string="Shortcut View",
        help="Preferred view type when clicking the shortcut button. "
        "Leave empty to stay on the current view.",
    )
    # Per-record whitelist of the view types that actually exist for this
    # filter's model. The filterable_selection widget reads it (via the
    # whitelist_fname option) to narrow the Shortcut View dropdown to views the
    # model has — the base selection above lists every switchable view type in
    # the system, this scopes it per model.
    shortcut_view_type_whitelist = fields.Json(
        compute="_compute_shortcut_view_type_whitelist",
    )
    shortcut_icon = fields.Char(
        string="Shortcut Icon",
        help="Font Awesome icon class for the shortcut button, e.g. fa-clock-o",
    )
    # Layout state captured from the view, stored as JSON.
    # For list views: {"optional_columns": [...], "column_widths": {...}}
    # For calendar views: {"scale": "week", "show_weekends": true}
    shortcut_layout = fields.Text(
        string="Shortcut Layout",
        help="JSON layout state captured from the view "
        "(column selection, widths, calendar scale, etc.)",
    )

    @api.model
    def _shortcut_view_type_selection(self):
        """All switchable (multi-record) view types registered in the system.

        Derived from ir.ui.view's own ``type`` selection, so custom view types
        (e.g. the credential planning timeline) are included automatically —
        no per-module selection_add on this field is needed. Non-switchable
        types (form / search / qweb) are dropped: a shortcut only ever switches
        between multi-record views.
        """
        view_types = self.env["ir.ui.view"].fields_get(["type"])["type"]["selection"]
        excluded = {"form", "search", "qweb"}
        return [(value, label) for value, label in view_types if value not in excluded]

    @api.depends("model_id")
    def _compute_shortcut_view_type_whitelist(self):
        """View types available for each filter's model: the switchable view
        types that have at least one ir.ui.view defined for the model. Feeds the
        filterable_selection widget so the Shortcut View dropdown cannot offer a
        view the model does not have. (Per-action availability is enforced
        separately, client-side, when the shortcut is clicked.)
        """
        switchable = {value for value, _label in self._shortcut_view_type_selection()}
        View = self.env["ir.ui.view"]
        for flt in self:
            available = []
            if flt.model_id:
                model_types = set(View.search([("model", "=", flt.model_id)]).mapped("type"))
                available = sorted(model_types & switchable)
            flt.shortcut_view_type_whitelist = available

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
            .read([
                "name",
                "shortcut_sequence",
                "shortcut_view_type",
                "shortcut_icon",
                "shortcut_layout",
            ])
        )
