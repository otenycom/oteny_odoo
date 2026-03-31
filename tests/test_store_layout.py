import json

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
