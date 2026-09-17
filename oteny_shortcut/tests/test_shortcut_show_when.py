from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("oteny_shortcut", "crewradar", "post_install", "-at_install", "test_store_layout")
class TestShortcutShowWhen(TransactionCase):
    """Where a shortcut button shows is a Python expression on the filter
    (shortcut_show_when), evaluated in the browser. The server side has three
    duties, tested here:

    - the expression must parse, so a typo cannot hide a shortcut everywhere;
    - get_filters (the favorites a view loads) carries the shortcut fields on
      every favorite and drops none: the browser decides per view whether a
      button shows and whether the shortcut's Default Filter applies;
    - get_shortcuts (the row above an in-form list) returns every shortcut of
      the model the user may see, whatever action it was saved from.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Filters = cls.env["ir.filters"]

        def make(name, **values):
            return Filters.create(
                {
                    "name": name,
                    "model_id": "res.partner",
                    "domain": "[]",
                    "context": "{}",
                    "sort": "[]",
                    **values,
                }
            )

        cls.everywhere_filter = make("Everywhere", shortcut_sequence=10)
        cls.form_filter = make(
            "In the partner form",
            shortcut_sequence=20,
            shortcut_show_when="subject == 'res.partner'",
            is_default=True,
            domain="[('is_company', '=', True)]",
        )
        # Saved from a specific action: hidden from other actions' banners by
        # Odoo's own rule, but a shortcut of the model inside any form.
        cls.action_filter = make(
            "From an action",
            shortcut_sequence=40,
            shortcut_show_when="view == 'form'",
            action_id=cls.env.ref("base.action_partner_form").id,
        )
        cls.plain_favorite = make("Plain favorite")

    def test_show_when_is_empty_by_default(self):
        self.assertFalse(self.everywhere_filter.shortcut_show_when)
        self.assertFalse(self.plain_favorite.shortcut_show_when)

    def test_show_when_must_parse(self):
        with self.assertRaises(ValidationError):
            self.everywhere_filter.shortcut_show_when = "subject =="
        # Valid expressions are accepted, whatever names they use: the
        # browser resolves the names.
        for expression in (
            "not subject",
            "subject in ('hr.employee', 'crewradar.site')",
            "view == 'calendar' and uid == 1",
            "  ",
        ):
            self.everywhere_filter.shortcut_show_when = expression

    def test_get_filters_carries_shortcut_fields_and_keeps_every_favorite(self):
        favorites = {f["id"]: f for f in self.env["ir.filters"].get_filters("res.partner")}
        for record in (self.everywhere_filter, self.form_filter, self.plain_favorite):
            self.assertIn(record.id, favorites)
        # Saved from another action: not a favorite of a call without action.
        self.assertNotIn(self.action_filter.id, favorites)

        everywhere = favorites[self.everywhere_filter.id]
        self.assertEqual(everywhere["shortcut_sequence"], 10)
        self.assertFalse(everywhere["shortcut_show_when"])
        for name in ("shortcut_view_type", "shortcut_icon", "shortcut_layout"):
            self.assertIn(name, everywhere)
        form = favorites[self.form_filter.id]
        self.assertEqual(form["shortcut_show_when"], "subject == 'res.partner'")
        # The default flag travels as stored; the browser cancels it where
        # the expression is false.
        self.assertTrue(form["is_default"])
        # A favorite that is not a shortcut still carries the keys, at rest.
        self.assertEqual(favorites[self.plain_favorite.id]["shortcut_sequence"], 0)

    def test_get_shortcuts_returns_every_shortcut_of_the_model(self):
        shortcuts = self.env["ir.filters"].get_shortcuts("res.partner")
        ids = [s["id"] for s in shortcuts]
        self.assertIn(self.everywhere_filter.id, ids)
        self.assertIn(self.form_filter.id, ids)
        # The action a filter was saved from does not matter inside a form.
        self.assertIn(self.action_filter.id, ids)
        self.assertNotIn(self.plain_favorite.id, ids)
        # Ordered by sequence; the row needs the domain, the default flag and
        # the expression.
        self.assertLess(ids.index(self.everywhere_filter.id), ids.index(self.form_filter.id))
        self.assertLess(ids.index(self.form_filter.id), ids.index(self.action_filter.id))
        by_id = {s["id"]: s for s in shortcuts}
        self.assertEqual(by_id[self.form_filter.id]["domain"], "[('is_company', '=', True)]")
        self.assertTrue(by_id[self.form_filter.id]["is_default"])
        self.assertEqual(by_id[self.form_filter.id]["shortcut_show_when"], "subject == 'res.partner'")
        self.assertFalse(by_id[self.everywhere_filter.id]["is_default"])
