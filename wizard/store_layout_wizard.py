import json

from markupsafe import Markup

from odoo import api, fields, models


class StoreLayoutWizard(models.TransientModel):
    _name = "shortcut.store.layout.wizard"
    _description = "Store Layout into Shortcut"

    filter_id = fields.Many2one(
        "ir.filters",
        string="Shortcut",
        required=True,
        readonly=True,
    )
    layout_json = fields.Text(
        string="Layout Data",
        required=True,
        readonly=True,
    )
    layout_summary = fields.Html(
        string="Layout Preview",
        compute="_compute_layout_summary",
    )

    @api.depends("layout_json")
    def _compute_layout_summary(self):
        for wizard in self:
            wizard.layout_summary = wizard._format_layout_summary()

    def _format_layout_summary(self):
        """Build a human-readable HTML summary of the captured layout."""
        if not self.layout_json:
            return ""
        try:
            data = json.loads(self.layout_json)
        except (json.JSONDecodeError, TypeError):
            return Markup("<em>Invalid layout data</em>")

        parts = []

        # List view layout
        optional_columns = data.get("optional_columns")
        if optional_columns is not None:
            cols_str = ", ".join(optional_columns) if optional_columns else "(none)"
            parts.append(f"<b>Visible optional columns:</b> {cols_str}")

        column_widths = data.get("column_widths")
        if column_widths:
            width_items = [
                f"{name}: {int(ratio * 100)}%"
                for name, ratio in column_widths.items()
            ]
            parts.append(
                f"<b>Column widths:</b> {', '.join(width_items)}"
            )

        # Calendar view layout
        scale = data.get("scale")
        if scale:
            parts.append(f"<b>Calendar scale:</b> {scale}")

        show_weekends = data.get("show_weekends")
        if show_weekends is not None:
            parts.append(
                f"<b>Show weekends:</b> {'Yes' if show_weekends else 'No'}"
            )

        if not parts:
            return Markup("<em>No layout data captured</em>")

        return Markup("<br/>".join(parts))

    def action_confirm(self):
        """Write the captured layout JSON to the target shortcut filter."""
        self.ensure_one()
        self.filter_id.shortcut_layout = self.layout_json
        return {"type": "ir.actions.act_window_close"}
