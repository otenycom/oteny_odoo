"""The generic Oteny bot activity log + its /json/2/ write-back seam (Layer 1, no domain)."""

from psycopg2 import IntegrityError

from odoo.addons.oteny_bot.models.oteny_bot import (
    ISOLATED_TURN_SENTINEL,
    VERBOSE_SENTINEL,
    WORK_HEADER_FMT,
)
from odoo.exceptions import UserError
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

    def test_ensure_bot_adopts_a_seeded_channel_bound_bot(self):
        # a business app seeds the bot (with its channel) but no uplink_ref; the write-back,
        # authenticated as the bot user, adopts it rather than forking a second record.
        seeded = self.env["oteny.bot"].create({"name": "Barney", "bot_user_id": self.env.uid})
        res = self.env["oteny.bot"].ensure_bot("hh00140", name="ignored")
        self.assertTrue(res["ok"] and res.get("adopted") and not res["created"])
        self.assertEqual(res["bot_id"], seeded.id)
        self.assertEqual(seeded.uplink_ref, "hh00140")
        self.assertEqual(seeded.name, "Barney")           # not renamed on adoption

    # --- the Discuss-flag dispatch (the trigger that replaces the harness poll) --- #

    def test_dispatch_isolated_turn_posts_a_flagged_message(self):
        channel = self.env["discuss.channel"].create({"name": "HR and Barney"})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh5", "discuss_channel_id": channel.id})
        res = bot.dispatch_isolated_turn("File the MFNL for placement 42")
        self.assertTrue(res["ok"])
        msg = self.env["mail.message"].browse(res["message_id"])
        self.assertEqual(msg.res_id, channel.id)
        self.assertIn(ISOLATED_TURN_SENTINEL, msg.body)   # the isolation flag the gateway parses
        self.assertIn("placement 42", msg.body)

    def test_dispatch_isolated_turn_needs_a_channel(self):
        bot = self.env["oteny.bot"].create({"name": "Barney", "uplink_ref": "hh6"})
        self.assertFalse(bot.dispatch_isolated_turn("x")["ok"])

    def test_dispatch_with_work_renders_the_header_and_token_trailer(self):
        # The WP1 wire: a token-fenced dispatch carries the machine-readable work header
        # (sentinel-adjacent, parsed by the hh-discuss adapter's WORK_HEADER_RE) plus the
        # token instructions the run needs for its bot_claim advances.
        channel = self.env["discuss.channel"].create({"name": "HR and Barney"})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh7", "discuss_channel_id": channel.id})
        res = bot.dispatch_isolated_turn(
            "File the MFNL for record 42",
            work={"res_model": "riverflow.service", "res_id": 42, "token": "tok_ABC-x9"})
        self.assertTrue(res["ok"])
        body = self.env["mail.message"].browse(res["message_id"]).body
        self.assertIn(ISOLATED_TURN_SENTINEL, body)
        self.assertIn(WORK_HEADER_FMT.format(
            res_model="riverflow.service", res_id=42, token="tok_ABC-x9"), body)
        self.assertIn("Your work token is tok_ABC-x9", body)
        self.assertIn("bot_token_check", body)

    def test_dispatch_without_work_stays_headerless(self):
        # tokenless isolated messages remain the plain legacy shape (scenario driver / chat)
        channel = self.env["discuss.channel"].create({"name": "Plain"})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh8", "discuss_channel_id": channel.id})
        body = self.env["mail.message"].browse(
            bot.dispatch_isolated_turn("hello")["message_id"]).body
        self.assertNotIn("[oteny:work:", body)
        self.assertNotIn("work token", body)

    def test_dispatch_verbose_flag_rides_the_body(self):
        # opt-in live-narration flag — off by default, present only when asked
        channel = self.env["discuss.channel"].create({"name": "HR and Barney"})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh9", "discuss_channel_id": channel.id})
        plain = self.env["mail.message"].browse(
            bot.dispatch_isolated_turn("run it")["message_id"]).body
        self.assertNotIn(VERBOSE_SENTINEL, plain)
        loud = self.env["mail.message"].browse(
            bot.dispatch_isolated_turn("run it", verbose=True)["message_id"]).body
        self.assertIn(VERBOSE_SENTINEL, loud)

    # --- record_run: the end-of-run write-back that ends the "silence" (D174 hybrid) --- #

    def _open_session(self, token="tokRUN", origin_id=17143):
        """Simulate the dispatch-time open session the state machine creates."""
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh00140"})
        return self.env["oteny.bot.session"].create({
            "bot_id": bot.id, "name": "MFNL filing", "kind": "isolated_turn",
            "request": "File the MFNL for #%s" % origin_id, "outcome": "dispatched",
            "work_token": token, "origin_model": "riverflow.service", "origin_res_id": origin_id})

    def test_record_run_adopts_the_token_matched_session_with_failure_reason(self):
        # THE regression: a 403-spiral run that used to sit silent as 'Dispatched' for 120 min
        # now lands as 'error' + the exact tool-failure breakdown, on the SAME session row.
        session = self._open_session(token="tokRUN")
        res = self.env["oteny.bot"].record_run(
            "tokRUN",
            run={"response": "()", "duration_s": 232.9, "outcome": "error",
                 "outcome_detail": "68/71 uplink calls failed: 55×403 access-denied "
                                   "(crewradar.site.type); empty final response"},
            turns=[{"sequence": 10, "tool_call_count": 71, "llm_response": "()",
                    "tool_calls": [{"name": "crewradar_json2", "result": "403"}]}])
        self.assertTrue(res["ok"])
        self.assertEqual(res["session_id"], session.id)   # ADOPTED, not forked
        session.invalidate_recordset()
        self.assertEqual(session.outcome, "error")
        self.assertIn("crewradar.site.type", session.outcome_detail)
        self.assertEqual(session.response, "()")
        self.assertEqual(session.turn_count, 1)
        self.assertEqual(session.tool_call_count, 71)

    def test_record_run_never_downgrades_a_terminal_state_machine_outcome(self):
        # if the workflow already closed the session (ok/escalated), a softer self-report fills
        # only forensics — the state machine keeps authority over the verdict.
        session = self._open_session(token="tokOK")
        session.outcome = "ok"
        self.env["oteny.bot"].record_run(
            "tokOK", run={"response": "Filed.", "outcome": "error", "outcome_detail": "guess"})
        session.invalidate_recordset()
        self.assertEqual(session.outcome, "ok")           # not clobbered
        self.assertFalse(session.outcome_detail)          # the soft detail was dropped too
        self.assertEqual(session.response, "Filed.")      # forensics still attached

    def test_record_run_healthy_run_leaves_outcome_to_the_state_machine(self):
        # a healthy run reports no outcome (outcome key absent) → session stays 'dispatched'
        # so the deterministic close can still set ok/escalated/timeout.
        session = self._open_session(token="tokH")
        self.env["oteny.bot"].record_run("tokH", run={"response": "Filed NL-MFNL-42."})
        session.invalidate_recordset()
        self.assertEqual(session.outcome, "dispatched")
        self.assertEqual(session.response, "Filed NL-MFNL-42.")

    def test_record_run_unknown_token_fails_cleanly(self):
        res = self.env["oteny.bot"].record_run("nope", run={"response": "x"})
        self.assertFalse(res["ok"])
        self.assertIn("no session", res["reason"])
        self.assertFalse(self.env["oteny.bot"].record_run("", run={})["ok"])

    # --- Bot Activity Watch / Replay (browser_session_ids + mint-on-click) --- #

    def test_record_run_accepts_browser_session_ids(self):
        session = self._open_session(token="tokBB")
        self.env["oteny.bot"].record_run(
            "tokBB",
            run={"response": "filing…",
                 "browser_session_ids": ["steel-sess-1", "steel-sess-2"]},
        )
        session.invalidate_recordset()
        self.assertEqual(session.browser_session_ids, ["steel-sess-1", "steel-sess-2"])
        self.assertTrue(session.has_browser_session)
        self.assertEqual(session.browser_status, "Live now")  # still dispatched

    def test_browser_status_replay_window_after_close(self):
        session = self._open_session(token="tokRP")
        session.write({
            "browser_session_ids": ["steel-sess-9"],
            "outcome": "ok",
            "duration_s": 30.0,
        })
        session.invalidate_recordset()
        self.assertTrue(session.has_browser_session)
        self.assertIn("Replay available", session.browser_status)

    def test_watch_live_opens_act_url_and_never_stores_it(self):
        from unittest.mock import patch
        session = self._open_session(token="tokW")
        session.browser_session_ids = ["steel-sess-w"]
        fake = {"session_id": "steel-sess-w",
                "session_viewer_url": "https://viewer.example/live?interactive=false"}
        with patch.object(
            type(self.env["oteny.broker.client"]),
            "_broker_post",
            return_value=fake,
        ) as mock_post:
            action = session.action_watch_live_browser()
        mock_post.assert_called_once()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["url"], fake["session_viewer_url"])
        # R3: the minted URL must not land on the session record.
        session.invalidate_recordset()
        self.assertEqual(session.browser_session_ids, ["steel-sess-w"])
        dumped = repr(session.read()[0])
        self.assertNotIn("viewer.example", dumped)

    def test_watch_live_friendly_404(self):
        from unittest.mock import patch
        session = self._open_session(token="tok404")
        session.browser_session_ids = ["gone"]
        with patch.object(
            type(self.env["oteny.broker.client"]),
            "_broker_post",
            side_effect=UserError("refused (404): unknown session"),
        ):
            with self.assertRaises(UserError) as err:
                session.action_watch_live_browser()
        self.assertIn("no longer available", str(err.exception).lower())
        self.assertNotIn("Steel", str(err.exception))

    def test_watch_without_browser_ids_is_friendly(self):
        session = self._open_session(token="tokNone")
        with self.assertRaises(UserError) as err:
            session.action_watch_live_browser()
        self.assertIn("did not use a cloud browser", str(err.exception))
