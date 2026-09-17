import json
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

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

    # ── Period: fixed dates or relative to today ────────────────────────
    #
    # A timeline view captures its window as `range_id` + `start_date` /
    # `stop_date` (ISO). Stored as-is, the shortcut always lands on those
    # fixed dates. Planners mostly want a window that moves with the
    # calendar ("last month through the next five"), so the wizard offers to
    # store the period RELATIVE to today instead: whole months counted from
    # the start of today's month, the same window shape the timeline scales
    # use. The offsets are prefilled from the captured dates and stay
    # editable before Confirm. Only a custom range has a period to choose
    # about; a scale (monthly, weekly, …) already means "its default window
    # around today".
    has_period = fields.Boolean(compute="_compute_has_period")
    period_mode = fields.Selection(
        [("fixed", "Fixed dates"), ("relative", "Relative to today")],
        string="Period",
        default="fixed",
    )
    start_month_offset = fields.Integer(
        string="Start month offset",
        compute="_compute_relative_defaults",
        readonly=False,
        store=True,
        help="Months between the start of today's month and the start of the "
        "period: 0 = this month, -1 = last month, 3 = three months ahead.",
    )
    length_months = fields.Integer(
        string="Length (months)",
        compute="_compute_relative_defaults",
        readonly=False,
        store=True,
        help="Number of whole months the period spans.",
    )

    def _layout(self):
        """The captured layout as a dict, or None when it is not valid JSON."""
        self.ensure_one()
        try:
            data = json.loads(self.layout_json or "")
        except (json.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _period_dates(layout):
        """(start, stop) dates of a fixed custom period, or None."""
        if not layout or layout.get("range_id") != "custom":
            return None
        try:
            start = fields.Date.from_string(layout.get("start_date"))
            stop = fields.Date.from_string(layout.get("stop_date"))
        except (ValueError, TypeError):
            return None
        if not start or not stop or start > stop:
            return None
        return start, stop

    @staticmethod
    def _relative_window(today, start_month_offset, length_months):
        """The dates a relative period resolves to on `today`: from the start
        of today's month shifted by the offset, `length_months` whole months."""
        start = today.replace(day=1) + relativedelta(months=start_month_offset)
        stop = start + relativedelta(months=max(length_months, 1)) - timedelta(days=1)
        return start, stop

    @api.depends("layout_json")
    def _compute_has_period(self):
        for wizard in self:
            wizard.has_period = bool(self._period_dates(wizard._layout()))

    @api.depends("layout_json")
    def _compute_relative_defaults(self):
        """Prefill the month offsets from the captured dates: the offset of the
        start date's month from today's month, and the number of months the
        window touches (a window that is not month-aligned snaps to whole
        months — the summary shows the resulting dates)."""
        for wizard in self:
            period = self._period_dates(wizard._layout())
            if not period:
                wizard.start_month_offset = 0
                wizard.length_months = 1
                continue
            start, stop = period
            today = fields.Date.context_today(wizard)
            wizard.start_month_offset = (start.year - today.year) * 12 + (
                start.month - today.month
            )
            wizard.length_months = max(
                (stop.year - start.year) * 12 + (stop.month - start.month) + 1, 1
            )

    @api.depends("layout_json", "period_mode", "start_month_offset", "length_months")
    def _compute_layout_summary(self):
        for wizard in self:
            wizard.layout_summary = wizard._format_layout_summary()

    def _format_layout_summary(self):
        """Build a human-readable HTML summary of the captured layout."""
        if not self.layout_json:
            return ""
        data = self._layout()
        if data is None:
            return Markup("<em>Invalid layout data</em>")

        parts = []
        handled = set()

        # List view layout
        optional_columns = data.get("optional_columns")
        if optional_columns is not None:
            cols_str = ", ".join(optional_columns) if optional_columns else "(none)"
            parts.append(f"<b>Visible optional columns:</b> {escape(cols_str)}")
            handled.add("optional_columns")

        column_widths = data.get("column_widths")
        if column_widths:
            width_items = [
                f"{escape(name)}: {int(ratio * 100)}%"
                for name, ratio in column_widths.items()
            ]
            parts.append(
                f"<b>Column widths:</b> {', '.join(width_items)}"
            )
        handled.add("column_widths")

        # Calendar view layout
        scale = data.get("scale")
        if scale:
            parts.append(f"<b>Calendar scale:</b> {escape(scale)}")
        handled.add("scale")

        show_weekends = data.get("show_weekends")
        if show_weekends is not None:
            parts.append(
                f"<b>Show weekends:</b> {'Yes' if show_weekends else 'No'}"
            )
        handled.add("show_weekends")

        # Timeline layout: scale id + period (fixed or relative to today)
        range_id = data.get("range_id")
        if range_id:
            parts.append(f"<b>Timeline scale:</b> {escape(range_id)}")
        handled.update({"range_id", "start_date", "stop_date", "relative_period"})
        period = self._period_dates(data)
        if period:
            today = fields.Date.context_today(self)
            if self.period_mode == "relative":
                start, stop = self._relative_window(
                    today, self.start_month_offset, self.length_months
                )
                parts.append(
                    "<b>Period:</b> relative to today — start month offset "
                    f"{self.start_month_offset:+d}, {max(self.length_months, 1)} month(s); "
                    f"as of today that is {start.strftime('%d-%b-%Y')} → "
                    f"{stop.strftime('%d-%b-%Y')}"
                )
            else:
                start, stop = period
                parts.append(
                    f"<b>Period:</b> fixed dates {start.strftime('%d-%b-%Y')} → "
                    f"{stop.strftime('%d-%b-%Y')}"
                )
        elif data.get("relative_period"):
            relative = data["relative_period"]
            parts.append(
                "<b>Period:</b> relative to today — start month offset "
                f"{int(relative.get('start_month_offset', 0)):+d}, "
                f"{int(relative.get('months', 1))} month(s)"
            )

        # Any other key a view stores (e.g. the timeline grouping mode) is
        # shown as-is so the confirmation never says "nothing captured"
        # for a layout that does carry data
        for key, value in data.items():
            if key not in handled:
                parts.append(f"<b>{escape(key)}:</b> {escape(json.dumps(value))}")

        if not parts:
            return Markup("<em>No layout data captured</em>")

        return Markup("<br/>".join(parts))

    def _final_layout_json(self):
        """The JSON to store: the captured layout, with a fixed custom period
        rewritten as a relative one when the user chose that."""
        self.ensure_one()
        data = self._layout()
        if self.period_mode != "relative" or not self._period_dates(data):
            return self.layout_json
        data.pop("start_date", None)
        data.pop("stop_date", None)
        data["relative_period"] = {
            "start_month_offset": self.start_month_offset,
            "months": max(self.length_months, 1),
        }
        return json.dumps(data)

    def action_confirm(self):
        """Write the captured layout JSON to the target shortcut filter."""
        self.ensure_one()
        self.filter_id.shortcut_layout = self._final_layout_json()
        return {"type": "ir.actions.act_window_close"}
