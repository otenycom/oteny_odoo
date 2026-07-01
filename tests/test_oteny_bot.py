"""The generic Oteny bot activity log + its /json/2/ write-back seam (Layer 1, no domain)."""

from psycopg2 import IntegrityError

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

    def test_ensure_bot_creates_once_and_is_idempotent(self):
        Bot = self.env["oteny.bot"]
        res = Bot.ensure_bot("hh00140", name="Barney")
        self.assertTrue(res["ok"] and res["created"])
        bot = Bot.browse(res["bot_id"])
        self.assertEqual(bot.uplink_ref, "hh00140")
        self.assertEqual(bot.name, "Barney")
        # a re-call is a no-op that returns the SAME bot and never renames it
        again = Bot.ensure_bot("hh00140", name="Renamed")
        self.assertTrue(again["ok"])
        self.assertFalse(again["created"])
        self.assertEqual(again["bot_id"], bot.id)
        self.assertEqual(bot.name, "Barney")

    def test_ensure_bot_defaults_name_to_uplink_ref(self):
        res = self.env["oteny.bot"].ensure_bot("hh00777")
        self.assertEqual(self.env["oteny.bot"].browse(res["bot_id"]).name, "hh00777")

    def test_uplink_ref_is_unique(self):
        # the DB constraint is what actually stops two bots forking one tenant's activity log
        self.env["oteny.bot"].create({"name": "A", "uplink_ref": "dup"})
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["oteny.bot"].create({"name": "B", "uplink_ref": "dup"}).flush_recordset()
