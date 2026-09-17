# test_audit_log_default_ignores.py
# Coverage for Measure 1: high-noise infrastructure models are ignored by default
# so they do not produce audit log rows. The set is centralised on
# oteny.audit.log._DEFAULT_IGNORED_MODEL_NAMES; a per-model override
# (`_oteny_audit_ignore = False`) re-enables audit when needed.
from odoo.tests import TransactionCase, tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogDefaultIgnores(TransactionCase):
    """Verify that mail/discuss/cron infrastructure models are default-ignored."""

    def setUp(self):
        super().setUp()
        self.log_model = self.env["oteny.audit.log"]

    def _audit_count_for(self, model_name, record_id):
        return self.log_model.search_count(
            [("model_name", "=", model_name), ("record_id", "=", record_id)]
        )

    def test_mail_message_is_audited_with_html_strip(self):
        """mail.message must NOT be default-ignored — it is the only durable
        copy of chatter content after a cascade unlink. See
        test_audit_log_chatter_preservation.py for the cascade-unlink coverage.
        """
        self.assertNotIn("mail.message", self.log_model._DEFAULT_IGNORED_MODEL_NAMES)
        self.assertFalse(self.log_model._is_audit_ignored("mail.message"))

        partner = self.env["res.partner"].create({"name": "Audit probe"})
        message = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": partner.id,
                "subject": "Probe",
                "body": "<p>Probe body</p>",
                "message_type": "comment",
            }
        )
        message.flush_recordset()

        # An audit row exists, with body stored as plain text.
        self.assertGreater(self._audit_count_for("mail.message", message.id), 0)

    def test_mail_mail_audit_ignored_by_default(self):
        """A freshly created mail.mail produces no audit log rows."""
        self.assertTrue(self.log_model._is_audit_ignored("mail.mail"))

        mail = self.env["mail.mail"].create(
            {
                "subject": "Probe",
                "body_html": "<p>Outgoing body</p>",
                "email_from": "audit@example.com",
                "email_to": "ignored@example.com",
            }
        )
        mail.flush_recordset()

        self.assertEqual(
            self._audit_count_for("mail.mail", mail.id),
            0,
            "mail.mail should produce no audit log rows by default",
        )

    def test_discuss_channel_audit_ignored_by_default(self):
        """A freshly created discuss.channel produces no audit log rows."""
        self.assertTrue(self.log_model._is_audit_ignored("discuss.channel"))

        channel = self.env["discuss.channel"].create(
            {"name": "Probe channel", "channel_type": "channel"}
        )
        channel.flush_recordset()

        self.assertEqual(
            self._audit_count_for("discuss.channel", channel.id),
            0,
            "discuss.channel should produce no audit log rows by default",
        )

    def test_mail_followers_audit_ignored_by_default(self):
        """mail.followers create/unlink does not produce audit rows."""
        self.assertTrue(self.log_model._is_audit_ignored("mail.followers"))

        partner = self.env["res.partner"].create({"name": "Follower probe"})
        # Subscribing creates a mail.followers row; we want zero audit rows for it.
        partner.message_subscribe(partner_ids=[partner.id])

        followers = self.env["mail.followers"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        # Whether or not subscribe created rows, none should be in the audit log.
        for f in followers:
            self.assertEqual(
                self._audit_count_for("mail.followers", f.id),
                0,
                "mail.followers should produce no audit log rows by default",
            )

    def test_default_ignored_can_be_reenabled_by_class_override(self):
        """Setting _oteny_audit_ignore = False on a default-ignored model class re-enables audit.

        Uses mail.mail (still in the default-ignore set) to exercise the
        override pathway. mail.message was moved out of the default-ignore set
        for chatter-preservation reasons (see test_audit_log_chatter_preservation).
        """
        # Pre-condition: mail.mail is ignored by default.
        self.assertTrue(self.log_model._is_audit_ignored("mail.mail"))

        # Locally override the class attribute and restore on cleanup so other tests are unaffected.
        cls = type(self.env["mail.mail"])
        had_attr = "_oteny_audit_ignore" in cls.__dict__
        old_value = cls._oteny_audit_ignore if had_attr else None
        cls._oteny_audit_ignore = False

        def restore():
            if had_attr:
                cls._oteny_audit_ignore = old_value
            else:
                del cls._oteny_audit_ignore

        self.addCleanup(restore)

        # With override, _is_audit_ignored returns False.
        self.assertFalse(self.log_model._is_audit_ignored("mail.mail"))

        # And a freshly created mail.mail now produces audit rows.
        mail = self.env["mail.mail"].create(
            {
                "subject": "Reenable probe",
                "body_html": "<p>Body</p>",
                "email_from": "probe@example.com",
                "email_to": "ignored@example.com",
            }
        )
        mail.flush_recordset()

        self.assertGreater(
            self._audit_count_for("mail.mail", mail.id),
            0,
            "mail.mail should produce audit logs when _oteny_audit_ignore is set to False",
        )

    def test_non_ignored_model_still_audited(self):
        """A normal business model not in the default-ignored set still produces audit logs."""
        # Use the existing test parent model which has _oteny_audit_ignore = False.
        self.assertFalse(self.log_model._is_audit_ignored("oteny.audit.test.parent"))

        parent = self.env["oteny.audit.test.parent"].create({"name": "Audited probe"})
        self.assertGreater(
            self._audit_count_for("oteny.audit.test.parent", parent.id),
            0,
            "Non-ignored business models should still be audited",
        )
