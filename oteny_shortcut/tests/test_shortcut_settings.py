from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.oteny_shortcut.models.ir_filters import (
    expression_for_preset,
    preset_for_expression,
)


@tagged("oteny_shortcut", "crewradar", "post_install", "-at_install", "test_store_layout")
class TestShortcutSettings(TransactionCase):
    """The shortcut settings on the filter form: Show as a button, Show in and
    Form read and write the stored position and Show When expression, so a
    user needs neither. Odoo's own rule says who may change a favorite: own
    and shared-with-all; a Settings admin, every one.
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
        )
        cls.custom = make(
            "Custom shortcut",
            shortcut_sequence=30,
            shortcut_show_when="view == 'kanban' and uid == 1",
        )
        cls.own_of_normal = make("Normal's own", user_ids=[(6, 0, [cls.normal_user.id])])
        cls.private_of_other = make("Other's private", user_ids=[(6, 0, [cls.other_user.id])])

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

    def test_settings_read_the_stored_values(self):
        self.assertTrue(self.form_shortcut.is_shortcut)
        self.assertEqual(self.form_shortcut.shortcut_show_preset, "subject")
        self.assertEqual(self.form_shortcut.shortcut_subject_model_id.model, "res.partner")

        self.assertFalse(self.plain.is_shortcut)
        self.assertEqual(self.plain.shortcut_show_preset, "everywhere")
        self.assertFalse(self.plain.shortcut_subject_model_id)

        self.assertEqual(self.custom.shortcut_show_preset, "custom")
        self.assertFalse(self.custom.shortcut_subject_model_id)

    def test_the_button_switch_gives_the_last_position(self):
        # On: after Form shortcut (20) and Custom (30).
        self.plain.is_shortcut = True
        self.assertEqual(self.plain.shortcut_sequence, 40)
        # On again does not move it.
        self.plain.is_shortcut = True
        self.assertEqual(self.plain.shortcut_sequence, 40)
        # Off: no shortcut any more.
        self.plain.is_shortcut = False
        self.assertEqual(self.plain.shortcut_sequence, 0)
        self.assertFalse(self.plain.is_shortcut)

    def test_the_choice_writes_the_expression(self):
        self.plain.shortcut_show_preset = "forms"
        self.assertEqual(self.plain.shortcut_show_when, "view == 'form'")

        self.plain.write(
            {
                "shortcut_show_preset": "subject",
                "shortcut_subject_model_id": self.env["ir.model"]._get("res.partner").id,
            }
        )
        self.assertEqual(self.plain.shortcut_show_when, "subject == 'res.partner'")

        self.plain.shortcut_show_preset = "views"
        self.assertEqual(self.plain.shortcut_show_when, "not subject")
        self.assertFalse(self.plain.shortcut_subject_model_id)

        self.plain.shortcut_show_preset = "everywhere"
        self.assertEqual(self.plain.shortcut_show_when, "")

        # Custom rule leaves the expression to the administrator.
        self.custom.shortcut_show_preset = "custom"
        self.assertEqual(self.custom.shortcut_show_when, "view == 'kanban' and uid == 1")
        self.custom.shortcut_show_when = "subject in ('a', 'b')"
        self.assertEqual(self.custom.shortcut_show_preset, "custom")

    def test_both_filter_forms_carry_the_shortcut_group(self):
        """The technical form (Settings > Technical > User-defined Filters) and
        the edit form Odoo opens with Edit right after saving a search, a
        primary inherit of it, both show the settings: there is no other door.
        """
        Filters = self.env["ir.filters"]
        for xml_id in ("base.ir_filters_view_form", "base.ir_filters_view_edit_form"):
            arch = Filters.get_view(view_id=self.env.ref(xml_id).id, view_type="form")["arch"]
            for field in ("is_shortcut", "shortcut_show_preset", "shortcut_subject_model_id", "shortcut_icon"):
                self.assertIn(f'name="{field}"', arch, (xml_id, field))

    def test_forms_offered_are_the_forms_that_list_the_records(self):
        models = self.plain.shortcut_subject_model_ids.mapped("model")
        # The contact form lists its contacts (child_ids), so it counts.
        self.assertIn("res.partner", models)
        self.assertFalse(any(self.plain.shortcut_subject_model_ids.mapped("transient")))
        # A model that only relates to contacts, without a list of them in
        # its form, is left out.
        self.assertNotIn("mail.followers", models)

    def test_a_user_changes_own_and_shared_favorites_only(self):
        own = self.own_of_normal.with_user(self.normal_user)
        own.is_shortcut = True
        self.assertGreater(self.own_of_normal.shortcut_sequence, 30)

        shared = self.plain.with_user(self.normal_user)
        shared.write({"is_shortcut": True, "shortcut_show_preset": "forms"})
        self.assertEqual(self.plain.shortcut_show_when, "view == 'form'")

        with self.assertRaises(AccessError):
            self.private_of_other.with_user(self.normal_user).write({"is_shortcut": True})
