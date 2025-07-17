from odoo import api, fields, models
from datetime import timedelta, datetime


class RiverflowHighlightRowMixin(models.AbstractModel):
    _name = "riverflow.highlight.row.mixin"
    _description = """Used to highlight rows in the list view, that have been edited in the last 10 seconds. 
This helps the user to visuallyfocus on the row when they just added a new row, or updated a row"""

    highlight_row = fields.Boolean(
        "Highlight Row",
        compute="_compute_highlight_row",
        store=False,
    )
    highlight_row_type = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Warning"),
            ("success", "Success"),
            ("danger", "Danger"),
            ("muted", "Muted"),
            ("primary", "Primary"),
        ],
        "Highlight Row Type",
        compute="_compute_highlight_row_type",
        store=False,
    )

    @api.depends("write_date")
    def _compute_highlight_row(self):
        for record in self:
            record.highlight_row = record.write_date > (datetime.now() - timedelta(seconds=10))

    def _compute_highlight_row_type(self):
        self.highlight_row_type = "info"
