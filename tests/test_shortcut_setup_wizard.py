from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.oteny_shortcut.wizard.shortcut_setup_wizard import (
    expression_for_preset,
    plural,
    preset_for_expression,
    with_article,
)


@tagged("oteny_shortcut", "crewradar", "post_install", "-at_install", "test_store_layout")
class TestShortcutSetupWizard(TransactionCase):
    """The Set Up Shortcut wizard: one favorite at a time, the Show presets
    that write the Show When expression, and Odoo's own rule on who may
    change a favorite (own and shared-with-all; a Settings admin, every one).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Filters = cls.env["ir.filters"]
        cls.other_user = cls.env["res.users"].create(
            {"name": "Other", "login": "shortcut_other", "group_ids": [(4, cls.env.ref("base.group_user").id)]}
        )
        cls.normal_user = cls.env["res.users"].create(
            {"name": "Normal", "login": "shortcut_normal", "group_ids": [(4, cls.env.ref("base.group_user").id)]}
        )

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

        cls.plain = make("Plain favorite")
        cls.form_shortcut = make(
            "Form shortcut",
            shortcut_sequence=20,
            shortcut_show_when="subject == 'res.partner'",
            is_default=True,
            shortcut_icon="fa-star",
        )
        cls.custom = make(
            "Custom shortcut",
            shortcut_sequence=30,
            shortcut_show_when="view == 'kanban' and uid == 1",
        )
        cls.own_of_normal = make("Normal's own", user_ids=[(6, 0, [cls.normal_user.id])])
        cls.private_of_other = make("Other's private", user_ids=[(6, 0, [cls.other_user.id])])

    def _wizard(self, filter_record, user=None, **context):
        Wizard = self.env["shortcut.setup.wizard"]
        if user:
            Wizard = Wizard.with_user(user)
        return Wizard.with_context(**context).create({"filter_id": filter_record.id})

    def test_preset_expression_round_trip(self):
        self.assertEqual(expression_for_preset("everywhere"), "")
        self.assertEqual(expression_for_preset("views"), "not subject")
        self.assertEqual(expression_for_preset("forms"), "view == 'form'")
        self.assertEqual(expression_for_preset("subject", "hr.employee"), "subject == 'hr.employee'")
        self.assertEqual(expression_for_preset("subject", None), "")
        self.assertEqual(preset_for_expression(""), ("everywhere", None))
        self.assertEqual(preset_for_expression(False), ("everywhere", None))
        self.assertEqual(preset_for_expression("not subject"), ("views", None))
        self.assertEqual(preset_for_expression(" view == 'form' "), ("forms", None))
        self.assertEqual(preset_for_expression('subject == "crewradar.site"'), ("subject", "crewradar.site"))
        self.assertEqual(preset_for_expression("subject in ('a', 'b')"), ("custom", None))

    def test_wizard_opens_on_what_the_favorite_holds(self):
        wizard = self._wizard(self.form_shortcut)
        self.assertEqual(wizard.res_model, "res.partner")
        self.assertTrue(wizard.is_shortcut)
        self.assertEqual(wizard.shortcut_sequence, 20)
        self.assertEqual(wizard.show_preset, "subject")
        self.assertEqual(wizard.subject_model_id.model, "res.partner")
        self.assertEqual(wizard.shortcut_show_when, "subject == 'res.partner'")
        self.assertEqual(wizard.shortcut_icon, "fa-star")
        self.assertTrue(wizard.is_default)

        wizard = self._wizard(self.plain)
        self.assertFalse(wizard.is_shortcut)
        self.assertEqual(wizard.shortcut_sequence, 0)
        self.assertEqual(wizard.show_preset, "everywhere")
        self.assertFalse(wizard.subject_model_id)
        self.assertFalse(wizard.is_default)

        wizard = self._wizard(self.custom)
        self.assertEqual(wizard.show_preset, "custom")
        self.assertEqual(wizard.shortcut_show_when, "view == 'kanban' and uid == 1")

    def test_confirm_writes_the_preset_expression(self):
        wizard = self._wizard(self.plain)
        wizard.is_shortcut = True
        wizard.show_preset = "forms"
        wizard.shortcut_icon = "fa-clock-o"
        self.assertEqual(wizard.shortcut_show_when, "view == 'form'")
        action = wizard.action_confirm()
        self.assertEqual(action["tag"], "reload")
        # A new button goes last: after Form shortcut (20) and Custom (30).
        self.assertEqual(self.plain.shortcut_sequence, 40)
        self.assertEqual(self.plain.shortcut_show_when, "view == 'form'")
        self.assertEqual(self.plain.shortcut_icon, "fa-clock-o")
        self.assertFalse(self.plain.is_default)

        # "Only in the form of ..." writes the chosen model; the gear inside a
        # form asks for a plain close instead of a page reload.
        wizard = self._wizard(self.plain, shortcut_wizard_no_reload=True)
        wizard.show_preset = "subject"
        wizard.subject_model_id = self.env["ir.model"]._get("res.partner")
        wizard.shortcut_sequence = 5
        wizard.is_default = True
        self.assertEqual(wizard.shortcut_show_when, "subject == 'res.partner'")
        action = wizard.action_confirm()
        self.assertEqual(action["type"], "ir.actions.act_window_close")
        self.assertEqual(self.plain.shortcut_sequence, 5)
        self.assertEqual(self.plain.shortcut_show_when, "subject == 'res.partner'")
        self.assertTrue(self.plain.is_default)

        # Button off: the favorite stays in the menu only; the order is cleared.
        wizard = self._wizard(self.plain)
        wizard.is_shortcut = False
        wizard.action_confirm()
        self.assertEqual(self.plain.shortcut_sequence, 0)

        # Custom keeps the text the user typed.
        wizard = self._wizard(self.custom)
        wizard.shortcut_show_when = "subject in ('a', 'b')"
        wizard.action_confirm()
        self.assertEqual(self.custom.shortcut_show_when, "subject in ('a', 'b')")

    def test_choices_are_worded_with_the_names_of_the_things(self):
        """Opened for a favorite, the Where choices name the favorite's model
        and the models that hold a list of it; without a favorite in the
        context they fall back to generic words. The keys never change.
        """
        Wizard = self.env["shortcut.setup.wizard"]
        labels = dict(Wizard.with_context(default_filter_id=self.plain.id)._show_preset_selection())
        self.assertEqual(list(labels), ["everywhere", "views", "forms", "subject", "custom"])
        self.assertEqual(labels["views"], "Only on the Contacts list")
        # Contacts are listed in dozens of forms: the label spells out a few
        # and ends with "...".
        self.assertTrue(labels["forms"].startswith("Only inside a"), labels["forms"])
        self.assertTrue(labels["forms"].endswith(", ..."), labels["forms"])
        self.assertEqual(labels["subject"], "Only inside one of them")

        # A short list is spelled out in full, with "or" before the last
        # name: bank accounts are listed in the Contact and Companies forms.
        bank_filter = self.env["ir.filters"].create(
            {"name": "Banks", "model_id": "res.partner.bank", "domain": "[]", "context": "{}", "sort": "[]"}
        )
        bank_labels = dict(Wizard.with_context(default_filter_id=bank_filter.id)._show_preset_selection())
        self.assertIn("Contact", bank_labels["forms"])
        self.assertIn(" or ", bank_labels["forms"])
        self.assertNotIn("...", bank_labels["forms"])

        fallback = dict(Wizard._show_preset_selection())
        self.assertEqual(fallback["views"], "Only on the list of all of them")

        self.assertEqual(plural("Service"), "Services")
        self.assertEqual(plural("Log Entry"), "Log Entries")
        self.assertEqual(plural("Address"), "Addresses")
        self.assertEqual(plural("Journey"), "Journeys")
        self.assertEqual(with_article("Employee"), "an Employee")
        self.assertEqual(with_article("Ship"), "a Ship")

    def test_subject_models_are_the_forms_that_list_the_records(self):
        wizard = self._wizard(self.plain)
        models = wizard.subject_model_ids.mapped("model")
        # The contact form lists its contacts (child_ids), so it counts.
        self.assertIn("res.partner", models)
        self.assertFalse(any(wizard.subject_model_ids.mapped("transient")))
        # A model that only relates to contacts, without a list of them in
        # its form, is left out: mail.followers points at res.partner with a
        # many2one only, and the mail message model relates through
        # partner_ids without a form list of contacts.
        self.assertNotIn("mail.followers", models)

    def test_gear_inside_a_form_prefills_the_form_model(self):
        wizard = self._wizard(self.plain, shortcut_subject_model="res.users")
        self.assertEqual(wizard.subject_model_id.model, "res.users")
        # Still "everywhere": the prefilled form is one click away, not chosen.
        self.assertEqual(wizard.show_preset, "everywhere")

    def test_a_user_changes_own_and_shared_favorites_only(self):
        wizard = self._wizard(self.own_of_normal, user=self.normal_user)
        wizard.is_shortcut = True
        wizard.action_confirm()
        self.assertGreater(self.own_of_normal.shortcut_sequence, 30)

        wizard = self._wizard(self.plain, user=self.normal_user)
        wizard.is_shortcut = True
        wizard.action_confirm()
        self.assertGreater(self.plain.shortcut_sequence, self.own_of_normal.shortcut_sequence)

        with self.assertRaises(AccessError):
            wizard = self._wizard(self.private_of_other, user=self.normal_user)
            wizard.is_shortcut = True
            wizard.action_confirm()
