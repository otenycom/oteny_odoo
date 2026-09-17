# test_audit_log_ignored_container.py
#
# Coverage for the per-RECORD audit skip: a `mail.message` posted into a container that is
# itself audit-ignored (a `discuss.channel`) produces no audit rows, while chatter on a real
# business record keeps producing them. `_is_audit_ignored` answers per MODEL and cannot
# express this, so the skip runs through `_oteny_audit_ignore_record` in base_patch, wired
# into all four emitting sites (create / write-relational / flush / unlink).
from odoo.tests import TransactionCase, tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditIgnoredContainer(TransactionCase):
    """Verify messages inside an audit-ignored container are not audited."""

    def setUp(self):
        super().setUp()
        self.log_model = self.env["oteny.audit.log"]
        self.channel = self.env["discuss.channel"].create(
            {"name": "Audit container probe", "channel_type": "channel"}
        )
        self.partner = self.env["res.partner"].create({"name": "Audit container parent"})

    def _audit_rows(self, message_id, change_type=None):
        domain = [("model_name", "=", "mail.message"), ("record_id", "=", message_id)]
        if change_type is not None:
            domain.append(("change_type", "=", change_type))
        return self.log_model.search(domain)

    def _post(self, model, res_id, subject="Probe"):
        message = self.env["mail.message"].create(
            {
                "model": model,
                "res_id": res_id,
                "subject": subject,
                "body": "<p>Probe body</p>",
                "message_type": "comment",
            }
        )
        message.flush_recordset()
        return message

    # --- the container rule --------------------------------------------------------- #

    def test_channel_is_audit_ignored_but_mail_message_is_not(self):
        """The precondition: the rule keys on an already-ignored container model."""
        self.assertTrue(self.log_model._is_audit_ignored("discuss.channel"))
        self.assertFalse(self.log_model._is_audit_ignored("mail.message"))

    def test_message_in_channel_produces_no_audit_rows(self):
        message = self._post("discuss.channel", self.channel.id)
        self.assertFalse(
            self._audit_rows(message.id),
            "a message posted into an audit-ignored channel must produce no audit rows",
        )

    def test_message_on_business_record_still_audited(self):
        """The control. Chatter on a real record keeps its tombstone — that guarantee is
        the whole reason mail.message is audited at all."""
        message = self._post("res.partner", self.partner.id)
        self.assertTrue(
            self._audit_rows(message.id, change_type="i"),
            "chatter on a business record must still produce an insert snapshot",
        )

    def test_message_without_a_target_model_is_still_audited(self):
        """A message with an empty `model` is deliberately NOT skipped. Zero such audited
        rows exist on the production-shaped database, so there is no measured noise to
        remove and no reason to widen the rule."""
        message = self.env["mail.message"].create(
            {"subject": "No target", "body": "<p>x</p>", "message_type": "comment"}
        )
        message.flush_recordset()
        self.assertTrue(self._audit_rows(message.id))

    # --- the rule holds on every emitting site -------------------------------------- #

    def test_update_of_a_channel_message_produces_no_audit_rows(self):
        """The flush path — a scalar write reaches patched_flush, not patched_write."""
        message = self._post("discuss.channel", self.channel.id)
        message.write({"subject": "Edited"})
        message.flush_recordset()
        self.assertFalse(self._audit_rows(message.id, change_type="u"))

    def test_delete_of_a_channel_message_produces_no_tombstone(self):
        message = self._post("discuss.channel", self.channel.id)
        message_id = message.id
        message.unlink()
        self.assertFalse(self._audit_rows(message_id, change_type="d"))

    def test_delete_of_a_business_record_message_still_tombstones(self):
        """The control for unlink: the cascade-preservation guarantee is untouched."""
        message = self._post("res.partner", self.partner.id)
        message_id = message.id
        message.unlink()
        self.assertEqual(len(self._audit_rows(message_id, change_type="d")), 1)

    # --- the hook itself ------------------------------------------------------------ #

    def test_hook_is_declared_only_where_it_is_needed(self):
        """A model without the hook must cost nothing — base_patch skips the call entirely."""
        self.assertTrue(hasattr(self.env["mail.message"], "_oteny_audit_ignore_record"))
        self.assertFalse(hasattr(self.env["res.partner"], "_oteny_audit_ignore_record"))
