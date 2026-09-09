import json
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged("oteny_shortcut", "crewradar", "post_install", "-at_install", "test_store_layout")
class TestStoreLayout(TransactionCase):
    """Test the Store Layout wizard and ir.filters shortcut_layout field."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.filter_record = cls.env["ir.filters"].create(
            {
                "name": "Test Shortcut",
                "model_id": "res.partner",
                "domain": "[]",
                "context": "{}",
                "sort": "[]",
                "shortcut_sequence": 10,
                "shortcut_view_type": "list",
            }
        )

    def test_wizard_confirm_stores_list_layout(self):
        """Confirming the wizard writes the layout JSON to the filter record."""
        layout = {
            "optional_columns": ["phone", "email", "city"],
            "column_widths": {"phone": 0.25, "email": 0.40, "city": 0.35},
        }
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(layout),
            }
        )
        result = wizard.action_confirm()
        self.assertEqual(result["type"], "ir.actions.act_window_close")
        self.assertEqual(
            json.loads(self.filter_record.shortcut_layout),
            layout,
        )

    def test_wizard_confirm_stores_calendar_layout(self):
        """Calendar layout with scale and weekend flag is stored correctly."""
        layout = {"scale": "week", "show_weekends": False}
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(layout),
            }
        )
        wizard.action_confirm()
        stored = json.loads(self.filter_record.shortcut_layout)
        self.assertEqual(stored["scale"], "week")
        self.assertFalse(stored["show_weekends"])

    def test_wizard_layout_summary_list(self):
        """Summary renders column names and width percentages for list layouts."""
        layout = {
            "optional_columns": ["phone", "email"],
            "column_widths": {"phone": 0.30, "email": 0.70},
        }
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(layout),
            }
        )
        summary = str(wizard.layout_summary)
        self.assertIn("phone", summary)
        self.assertIn("email", summary)
        self.assertIn("30%", summary)
        self.assertIn("70%", summary)

    def test_wizard_layout_summary_calendar(self):
        """Summary renders scale and weekends flag for calendar layouts."""
        layout = {"scale": "month", "show_weekends": True}
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(layout),
            }
        )
        summary = str(wizard.layout_summary)
        self.assertIn("month", summary)
        self.assertIn("Yes", summary)

    def test_wizard_layout_summary_empty(self):
        """Empty layout JSON produces 'no layout data' message."""
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": "{}",
            }
        )
        summary = str(wizard.layout_summary)
        self.assertIn("No layout data", summary)

    def test_wizard_layout_summary_invalid_json(self):
        """Invalid JSON produces error message instead of crashing."""
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": "not json",
            }
        )
        summary = str(wizard.layout_summary)
        self.assertIn("Invalid", summary)

    def test_get_shortcuts_returns_layout(self):
        """get_shortcuts() includes the shortcut_layout field for JS consumption."""
        layout = {"scale": "day", "show_weekends": True}
        self.filter_record.shortcut_layout = json.dumps(layout)
        shortcuts = self.env["ir.filters"].get_shortcuts("res.partner")
        match = [s for s in shortcuts if s["id"] == self.filter_record.id]
        self.assertTrue(match, "Filter should appear in shortcuts")
        self.assertEqual(
            json.loads(match[0]["shortcut_layout"]),
            layout,
        )

    def test_get_shortcuts_layout_is_none_when_empty(self):
        """Shortcut layout is False when not set."""
        self.filter_record.shortcut_layout = False
        shortcuts = self.env["ir.filters"].get_shortcuts("res.partner")
        match = [s for s in shortcuts if s["id"] == self.filter_record.id]
        self.assertTrue(match)
        self.assertFalse(match[0]["shortcut_layout"])

    def test_overwrite_existing_layout(self):
        """Storing a new layout overwrites the previous one."""
        old_layout = {"optional_columns": ["phone"]}
        self.filter_record.shortcut_layout = json.dumps(old_layout)

        new_layout = {
            "optional_columns": ["phone", "email"],
            "column_widths": {"phone": 0.50, "email": 0.50},
        }
        wizard = self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(new_layout),
            }
        )
        wizard.action_confirm()
        self.assertEqual(
            json.loads(self.filter_record.shortcut_layout),
            new_layout,
        )

    # ── Timeline period: fixed dates or relative to today ───────────────

    def _timeline_wizard(self, layout, **values):
        return self.env["shortcut.store.layout.wizard"].create(
            {
                "filter_id": self.filter_record.id,
                "layout_json": json.dumps(layout),
                **values,
            }
        )

    def test_timeline_fixed_period_is_stored_as_captured(self):
        """The default Period choice keeps the captured dates untouched."""
        layout = {
            "range_id": "custom",
            "start_date": "2026-08-01",
            "stop_date": "2027-01-31",
            "grouping_mode": "byShip",
        }
        wizard = self._timeline_wizard(layout)
        self.assertTrue(wizard.has_period)
        self.assertEqual(wizard.period_mode, "fixed")
        wizard.action_confirm()
        self.assertEqual(json.loads(self.filter_record.shortcut_layout), layout)
        summary = str(wizard.layout_summary)
        self.assertIn("fixed dates 01-Aug-2026", summary)
        self.assertIn("31-Jan-2027", summary)
        # Keys the wizard does not know are still shown, never "nothing captured"
        self.assertIn("grouping_mode", summary)
        self.assertIn("byShip", summary)

    def test_timeline_relative_period_prefill_and_store(self):
        """Relative to today: the month offsets are prefilled from the captured
        dates, stay editable, and replace the fixed dates on confirm."""
        today = fields.Date.context_today(self.filter_record)
        month_start = today.replace(day=1)
        start = month_start - relativedelta(months=1)
        stop = month_start + relativedelta(months=5) - timedelta(days=1)
        layout = {
            "range_id": "custom",
            "start_date": fields.Date.to_string(start),
            "stop_date": fields.Date.to_string(stop),
        }
        wizard = self._timeline_wizard(layout, period_mode="relative")
        # "last month through the next five": -1 and 6
        self.assertEqual(wizard.start_month_offset, -1)
        self.assertEqual(wizard.length_months, 6)

        wizard.length_months = 3
        summary = str(wizard.layout_summary)
        self.assertIn("relative to today", summary)
        self.assertIn(start.strftime("%d-%b-%Y"), summary)
        expected_stop = start + relativedelta(months=3) - timedelta(days=1)
        self.assertIn(expected_stop.strftime("%d-%b-%Y"), summary)

        wizard.action_confirm()
        stored = json.loads(self.filter_record.shortcut_layout)
        self.assertEqual(
            stored,
            {"range_id": "custom", "relative_period": {"start_month_offset": -1, "months": 3}},
        )

    def test_timeline_scale_has_no_period_choice(self):
        """A scale already means 'its default window around today'."""
        wizard = self._timeline_wizard({"range_id": "monthly", "grouping_mode": "byEmployee"})
        self.assertFalse(wizard.has_period)
        wizard.period_mode = "relative"
        wizard.action_confirm()
        self.assertEqual(
            json.loads(self.filter_record.shortcut_layout),
            {"range_id": "monthly", "grouping_mode": "byEmployee"},
        )
        self.assertIn("monthly", str(wizard.layout_summary))

    def test_relative_window_snaps_to_whole_months(self):
        """A captured window that is not month-aligned prefills whole months."""
        today = fields.Date.context_today(self.filter_record)
        layout = {
            "range_id": "custom",
            "start_date": fields.Date.to_string(today.replace(day=15)),
            "stop_date": fields.Date.to_string(today.replace(day=15) + relativedelta(months=2)),
        }
        wizard = self._timeline_wizard(layout, period_mode="relative")
        self.assertEqual(wizard.start_month_offset, 0)
        self.assertEqual(wizard.length_months, 3)
        start, stop = wizard._relative_window(today, 0, 3)
        self.assertEqual(start, today.replace(day=1))
        self.assertEqual(stop, today.replace(day=1) + relativedelta(months=3) - timedelta(days=1))
