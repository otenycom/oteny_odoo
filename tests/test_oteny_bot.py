"""The generic Oteny bot activity log + its /json/2/ write-back seam (Layer 1, no domain)."""

from odoo.tests import TransactionCase, tagged


@tagged("oteny_bot", "post_install", "-at_install")
class TestOtenyBot(TransactionCase):
    def test_record_activity_creates_session_and_turns(self):
        bot = self.env["oteny.bot"].create({"name": "TestBot", "uplink_ref": "hh09999"})
        res = self.env["oteny.bot"].record_activity(
            "hh09999",
            {"name": "File MFNL for Becoy", "kind": "isolated_turn",
             "request": "File the MFNL.", "response": "Filed NL-MFNL-123.", "outcome": "ok",
             "origin_model": "riverflow.service", "origin_res_id": 42, "duration_s": 3.5},
            turns=[{"sequence": 10, "llm_model": "claude", "tool_calls": [{"name": "browser"}],
                    "tool_call_count": 1, "llm_response": "done"}])
        self.assertTrue(res["ok"])
        s = self.env["oteny.bot.session"].browse(res["session_id"])
        self.assertEqual(s.bot_id, bot)
        self.assertEqual(s.outcome, "ok")
        # the SOFT origin ref lets a workflow/app module attach without a hard FK up
        self.assertEqual(s.origin_model, "riverflow.service")
        self.assertEqual(s.origin_res_id, 42)
        self.assertEqual(s.turn_count, 1)
        self.assertEqual(s.tool_call_count, 1)

    def test_record_activity_unknown_bot_fails_cleanly(self):
        res = self.env["oteny.bot"].record_activity("nope", {"name": "x"})
        self.assertFalse(res["ok"])
        self.assertIn("uplink_ref", res["reason"])

    def test_record_activity_ignores_unknown_fields(self):
        # forward-compat: a bot on a newer schema may send a key this Odoo lacks — drop it, don't crash.
        self.env["oteny.bot"].create({"name": "B", "uplink_ref": "hh1"})
        res = self.env["oteny.bot"].record_activity("hh1", {"name": "x", "bogus_field": 1})
        self.assertTrue(res["ok"])

    def test_bot_session_count(self):
        bot = self.env["oteny.bot"].create({"name": "C", "uplink_ref": "hh2"})
        for i in range(3):
            self.env["oteny.bot"].record_activity("hh2", {"name": f"run {i}", "outcome": "ok"})
        self.assertEqual(bot.session_count, 3)
