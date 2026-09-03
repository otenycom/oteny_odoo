"""Contacts proof for ``oteny.form.session``.

A bot browses the same list and form a person already has on
``res.partner``. This file calls the adapter only. It does not import
``odoo.tests.form.Form``. It does not import riverflow.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("oteny_bot", "post_install", "-at_install", "test_form_session")
class TestFormSessionPartner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Session = cls.env["oteny.form.session"]

    def test_views_partner(self):
        result = self.Session.views("res.partner")
        xmlids = {row.get("xmlid") for row in result.get("actions", [])}
        xmlids.update(row.get("xmlid") for row in result.get("views", []))
        self.assertIn("base.action_partner_form", xmlids)
        self.assertIn("base.view_partner_tree", xmlids)
        self.assertIn("base.view_partner_form", xmlids)

    def test_list_partner_visible_columns(self):
        partner = self.env["res.partner"].create({
            "name": "Form Session List Probe",
            "email": "list-probe@example.com",
            "phone": "+31000000001",
        })
        result = self.Session.list(
            action="base.action_partner_form",
            domain=[("name", "=", partner.name)],
        )
        record = next(
            (row for row in result["records"] if row.get("id") == partner.id),
            None,
        )
        self.assertIsNotNone(record)
        self.assertIn("display_name", record)
        self.assertIn("email", record)
        self.assertIn("phone", record)
        self.assertEqual(record["email"], partner.email)
        self.assertNotIn("avatar_128", record)
        self.assertNotIn("application_statistics", record)

    def test_create_partner(self):
        photo = self.Session.open(
            action="base.action_partner_form",
        )
        handle = photo["handle"]
        names = {field["name"] for field in photo["fields"]}
        self.assertIn("name", names)
        self.assertNotIn("is_company", names)
        photo = self.Session.set(handle, {"name": "Form Session Ada"})
        saved = self.Session.save(handle)
        partner = self.env["res.partner"].browse(saved["res_id"])
        self.assertTrue(partner.exists())
        self.assertEqual(partner.name, "Form Session Ada")

    def test_onchange_company_type(self):
        photo = self.Session.open(view="base.view_partner_form")
        handle = photo["handle"]
        names = {field["name"] for field in photo["fields"]}
        self.assertNotIn("is_company", names)
        self.assertIn("company_type", names)
        self.Session.set(handle, {
            "name": "Form Session Company",
            "company_type": "company",
        })
        saved = self.Session.save(handle)
        partner = self.env["res.partner"].browse(saved["res_id"])
        self.assertTrue(partner.is_company)

    def test_refuse_set_hidden_or_unknown(self):
        photo = self.Session.open(view="base.view_partner_form")
        handle = photo["handle"]
        self.Session.set(handle, {"name": "Form Session Refuse"})
        with self.assertRaises(UserError):
            self.Session.set(handle, {"is_company": True})
        with self.assertRaises(UserError):
            self.Session.set(handle, {"no_such_partner_field": 1})
        saved = self.Session.save(handle)
        partner = self.env["res.partner"].browse(saved["res_id"])
        self.assertFalse(partner.is_company)
        self.assertEqual(partner.name, "Form Session Refuse")

    def test_edit_and_delete_partner(self):
        partner = self.env["res.partner"].create({
            "name": "Form Session Edit",
            "email": "old@example.com",
        })
        photo = self.Session.open(
            view="base.view_partner_form",
            res_id=partner.id,
        )
        handle = photo["handle"]
        self.Session.set(handle, {"email": "new@example.com"})
        self.Session.save(handle)
        self.assertEqual(partner.email, "new@example.com")

        self.Session.unlink_record(handle)
        self.assertFalse(partner.exists())
        listed = self.Session.list(
            view="base.view_partner_tree",
            domain=[("name", "=", "Form Session Edit")],
        )
        self.assertFalse(
            any(row.get("id") == partner.id for row in listed["records"])
        )

    def test_handle_expired(self):
        photo = self.Session.open(view="base.view_partner_form")
        handle = photo["handle"]
        self.Session.browse(handle).unlink()
        with self.assertRaises(UserError) as ctx:
            self.Session.set(handle, {"name": "gone"})
        self.assertIn("handle-expired", str(ctx.exception))
