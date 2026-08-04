"""The generic Oteny bot activity log + its /json/2/ write-back seam (Layer 1, no domain)."""

from psycopg2 import IntegrityError

from odoo import Command
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

    def test_ensure_bot_rehomes_stale_same_user_uplink_ref(self):
        # --fresh destroys the box but leaves the seeded row on the old uplink_ref.
        # Rehome that row; do not fork a second bot (xmlid Hand-to-Barney stays live).
        seeded = self.env["oteny.bot"].create({
            "name": "Barney", "uplink_ref": "hh00396", "bot_user_id": self.env.uid,
        })
        res = self.env["oteny.bot"].ensure_bot("hh00397", name="ignored")
        self.assertTrue(res["ok"] and res.get("rehomed") and not res["created"])
        self.assertEqual(res["bot_id"], seeded.id)
        self.assertEqual(seeded.uplink_ref, "hh00397")
        self.assertEqual(seeded.name, "Barney")
        self.assertEqual(
            self.env["oteny.bot"].search_count([("bot_user_id", "=", self.env.uid)]), 1)

    def test_ensure_bot_collapses_channel_less_fork_onto_seed(self):
        # Bad prior provision already forked: seed keeps old ref; fork has the new ref.
        # ensure_bot must collapse onto the seed and deactivate the fork.
        seed = self.env["oteny.bot"].create({
            "name": "Barney", "uplink_ref": "hh00396", "bot_user_id": self.env.uid,
        })
        channel = self.env["discuss.channel"].create({"name": "Bot Room"})
        fork = self.env["oteny.bot"].create({
            "name": "hh00397", "uplink_ref": "hh00397",
            "bot_user_id": self.env.uid, "discuss_channel_id": channel.id,
        })
        res = self.env["oteny.bot"].ensure_bot("hh00397")
        self.assertTrue(res["ok"] and res.get("rehomed"))
        self.assertEqual(res["bot_id"], seed.id)
        self.assertEqual(seed.uplink_ref, "hh00397")
        self.assertEqual(seed.discuss_channel_id, channel)
        self.assertFalse(fork.active)
        self.assertFalse(fork.discuss_channel_id)

    def test_bind_discuss_channel_rehomes_seeded_bot_onto_new_ref(self):
        # Second provision rehomes the seeded xmlid row onto the new uplink_ref and
        # keeps the HR channel there (never a mute seed + channel-holding fork).
        channel = self.env["discuss.channel"].create({"name": "Bot Room"})
        seeded = self.env["oteny.bot"].create({
            "name": "Barney", "uplink_ref": "hh00394",
            "bot_user_id": self.env.uid, "discuss_channel_id": channel.id,
        })
        res = self.env["oteny.bot"].bind_discuss_channel("hh00395")
        self.assertTrue(res["ok"])
        self.assertEqual(res["bot_id"], seeded.id)
        self.assertEqual(seeded.uplink_ref, "hh00395")
        self.assertEqual(seeded.discuss_channel_id, channel)
        self.assertEqual(
            self.env["oteny.bot"].search_count([
                ("bot_user_id", "=", self.env.uid), ("active", "=", True)]), 1)

    def test_bind_discuss_channel_with_explicit_channel_id(self):
        channel = self.env["discuss.channel"].create({"name": "HR"})
        res = self.env["oteny.bot"].bind_discuss_channel("hh00396", channel_id=channel.id)
        self.assertTrue(res["ok"])
        bot = self.env["oteny.bot"].browse(res["bot_id"])
        self.assertEqual(bot.discuss_channel_id, channel)

    # --- the Discuss-flag dispatch (the trigger that replaces the harness poll) --- #

    def test_dispatch_isolated_turn_posts_a_flagged_message(self):
        channel = self.env["discuss.channel"].create({"name": "Bot Room"})
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
        channel = self.env["discuss.channel"].create({"name": "Bot Room"})
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
        channel = self.env["discuss.channel"].create({"name": "Bot Room"})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": "hh9", "discuss_channel_id": channel.id})
        plain = self.env["mail.message"].browse(
            bot.dispatch_isolated_turn("run it")["message_id"]).body
        self.assertNotIn(VERBOSE_SENTINEL, plain)
        loud = self.env["mail.message"].browse(
            bot.dispatch_isolated_turn("run it", verbose=True)["message_id"]).body
        self.assertIn(VERBOSE_SENTINEL, loud)

    # --- D248: role channels + the channel admission verdict ------------------------- #

    def _bot_with_seam_user(self, login="seam.bot", ref="hhD248", operator=False):
        """A bot with its own seam login (what channels_for_bot identifies it by)."""
        groups = [self.env.ref("base.group_user").id]
        if operator:
            groups.append(self.env.ref("oteny_bot.group_oteny_bot_operator").id)
        user = self.env["res.users"].create({
            "name": "Seam Bot", "login": login, "group_ids": [Command.set(groups)]})
        bot = self.env["oteny.bot"].create(
            {"name": "Barney", "uplink_ref": ref, "bot_user_id": user.id})
        return bot, user

    def _room(self, name, creator, members):
        """A Discuss channel created BY ``creator`` with exactly ``members`` as partners."""
        return self.env["discuss.channel"].with_user(creator).create({
            "name": name,
            "channel_member_ids": [
                Command.create({"partner_id": p.id}) for p in members],
        })

    def test_dispatch_role_targets_the_bound_room(self):
        # The dedicated lane: a workflow's dispatches must land in the room bound to its
        # role, so the run starts with that role's persona + preloaded skills — not in
        # whatever casual room happens to share the bot.
        home = self.env["discuss.channel"].create({"name": "Crew Ops"})
        lane = self.env["discuss.channel"].create({"name": "Barney MFNL Filing"})
        bot = self.env["oteny.bot"].create({
            "name": "Barney", "uplink_ref": "hhROLE", "discuss_channel_id": home.id,
            "channel_ids": [Command.create({"role": "mfnl_filing",
                                            "channel_id": lane.id})]})
        res = bot.dispatch_isolated_turn("File it", role="mfnl_filing")
        self.assertEqual(res["channel_id"], lane.id)
        self.assertEqual(
            self.env["mail.message"].browse(res["message_id"]).res_id, lane.id)
        # no role, or a role nobody bound → the home channel, never nowhere
        self.assertEqual(bot.dispatch_isolated_turn("hi")["channel_id"], home.id)
        self.assertEqual(
            bot.dispatch_isolated_turn("hi", role="unbound")["channel_id"], home.id)

    def test_a_role_can_only_be_bound_once_per_bot(self):
        a = self.env["discuss.channel"].create({"name": "A"})
        b = self.env["discuss.channel"].create({"name": "B"})
        bot = self.env["oteny.bot"].create({"name": "Barney", "uplink_ref": "hhUNIQ"})
        self.env["oteny.bot.channel"].create(
            {"bot_id": bot.id, "role": "mfnl_filing", "channel_id": a.id})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["oteny.bot.channel"].create(
                {"bot_id": bot.id, "role": "mfnl_filing", "channel_id": b.id})

    def test_channels_for_bot_returns_home_and_declared_roles(self):
        # The declared lane is served on the strength of the CONFIGURATION, so it holds
        # even with autoauth off on the Oteny side (the adapter keeps `declared` rooms).
        bot, user = self._bot_with_seam_user(login="seam.declared", ref="hhDECL")
        home = self.env["discuss.channel"].create({"name": "Crew Ops"})
        lane = self.env["discuss.channel"].create({"name": "Barney MFNL Filing"})
        bot.discuss_channel_id = home
        self.env["oteny.bot.channel"].create(
            {"bot_id": bot.id, "role": "mfnl_filing", "channel_id": lane.id})
        out = self.env["oteny.bot"].with_user(user).channels_for_bot()
        self.assertTrue(out["ok"])
        by_id = {c["id"]: c for c in out["channels"]}
        self.assertEqual(by_id[home.id], {"id": home.id, "name": "Crew Ops",
                                          "role": "", "declared": True})
        self.assertEqual(by_id[lane.id]["role"], "mfnl_filing")
        self.assertTrue(by_id[lane.id]["declared"])

    def test_channels_for_bot_names_the_home_channels_role_when_they_are_one_room(self):
        # The common single-room deployment: the client binds the role to the SAME room
        # that is already the home channel. It must come back once, WITH the role — a
        # duplicate row (or a role-less home entry) would run the lane personaless.
        bot, user = self._bot_with_seam_user(login="seam.oneroom", ref="hhONE")
        room = self.env["discuss.channel"].create({"name": "Barney MFNL Filing"})
        bot.discuss_channel_id = room
        self.env["oteny.bot.channel"].create(
            {"bot_id": bot.id, "role": "mfnl_filing", "channel_id": room.id})
        rows = self.env["oteny.bot"].with_user(user).channels_for_bot()["channels"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "mfnl_filing")

    def test_channels_for_bot_autoauths_an_operators_all_internal_room(self):
        # The casual lane: an operator adds the bot to a staff room and it answers there.
        bot, seam = self._bot_with_seam_user(login="seam.casual", ref="hhCASUAL")
        operator = self.env["res.users"].create({
            "name": "Kirsten", "login": "kirsten.d248", "group_ids": [Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("oteny_bot.group_oteny_bot_operator").id])]})
        room = self._room("Crew Ops", operator,
                          [operator.partner_id, seam.partner_id])
        out = self.env["oteny.bot"].with_user(seam).channels_for_bot()
        casual = [c for c in out["channels"] if c["id"] == room.id]
        self.assertEqual(casual, [{"id": room.id, "name": "Crew Ops",
                                   "role": "", "declared": False}])
        self.assertNotIn(room.id, [s["id"] for s in out["skipped"]])

    def test_channels_for_bot_refuses_the_auto_subscription_general_channel(self):
        # Gate 0 — SOMEBODY ACTUALLY ADDED IT. Odoo's `general` channel carries
        # group_ids = Employees, which auto-subscribes every internal user the moment it is
        # created — including the bot's seam login. Without this gate every bot silently
        # wakes up company-wide on day one, in a room nobody chose to put it in (and it
        # passes the other two gates: created by the system admin, all-internal members).
        bot, seam = self._bot_with_seam_user(login="seam.general", ref="hhGEN")
        general = self.env.ref("mail.channel_all_employees")
        self.assertTrue(general.group_ids, "premise: general auto-subscribes a group")
        self.assertIn(seam.partner_id, general.channel_partner_ids,
                      "premise: a new internal user is auto-subscribed to general")
        out = self.env["oteny.bot"].with_user(seam).channels_for_bot()
        self.assertEqual([c["id"] for c in out["channels"]], [])
        self.assertIn("auto-subscription", out["skipped"][0]["reason"])

    def test_channels_for_bot_refuses_a_room_a_non_operator_made(self):
        # Gate 1 — WHO put it there. Otherwise any internal user could conjure a room,
        # drop the bot in, and get an agent reading this Odoo through the bot's grants.
        bot, seam = self._bot_with_seam_user(login="seam.gate1", ref="hhGATE1")
        plain = self.env["res.users"].create({
            "name": "Nosy", "login": "nosy.d248",
            "group_ids": [Command.set([self.env.ref("base.group_user").id])]})
        room = self._room("Shadow Room", plain, [plain.partner_id, seam.partner_id])
        out = self.env["oteny.bot"].with_user(seam).channels_for_bot()
        self.assertEqual([c["id"] for c in out["channels"]], [])
        refusal = {s["id"]: s["reason"] for s in out["skipped"]}
        self.assertIn("Operator", refusal[room.id])

    def test_channels_for_bot_refuses_a_room_with_an_outside_reader(self):
        # Gate 2 — WHO can read the answers. The bot quotes employee and client data, so a
        # room holding a portal user is refused outright rather than quietly served.
        bot, seam = self._bot_with_seam_user(login="seam.gate2", ref="hhGATE2")
        operator = self.env["res.users"].create({
            "name": "Kirsten", "login": "kirsten.gate2", "group_ids": [Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("oteny_bot.group_oteny_bot_operator").id])]})
        portal = self.env["res.users"].create({
            "name": "Client", "login": "client.gate2",
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])]})
        room = self._room("Client Room", operator,
                          [operator.partner_id, portal.partner_id, seam.partner_id])
        out = self.env["oteny.bot"].with_user(seam).channels_for_bot()
        self.assertEqual([c["id"] for c in out["channels"]], [])
        refusal = {s["id"]: s["reason"] for s in out["skipped"]}
        self.assertIn("non-internal", refusal[room.id])

    def test_channels_for_bot_declared_room_skips_the_autoauth_gates(self):
        # A binding is a deliberate act by whoever configured the bot, so it outranks the
        # creator gate — otherwise a room seeded by module data (create_uid = the installing
        # admin at some past upgrade) could fall out of the set on a later restore.
        bot, seam = self._bot_with_seam_user(login="seam.declgate", ref="hhDG")
        plain = self.env["res.users"].create({
            "name": "Plain", "login": "plain.declgate",
            "group_ids": [Command.set([self.env.ref("base.group_user").id])]})
        room = self._room("Filing", plain, [plain.partner_id, seam.partner_id])
        self.env["oteny.bot.channel"].create(
            {"bot_id": bot.id, "role": "mfnl_filing", "channel_id": room.id})
        out = self.env["oteny.bot"].with_user(seam).channels_for_bot()
        self.assertEqual([c["id"] for c in out["channels"]], [room.id])
        self.assertNotIn(room.id, [s["id"] for s in out["skipped"]])

    def test_channels_for_bot_never_answers_for_another_bot(self):
        # The verdict is keyed off the AUTHENTICATED login, never an argument — a
        # compromised uplink key cannot enumerate another bot's rooms, and a login with no
        # bot behind it gets nothing rather than someone else's set.
        _bot_a, seam_a = self._bot_with_seam_user(login="seam.a", ref="hhA")
        bot_b, _seam_b = self._bot_with_seam_user(login="seam.b", ref="hhB")
        bot_b.discuss_channel_id = self.env["discuss.channel"].create({"name": "B room"})
        self.assertEqual(
            self.env["oteny.bot"].with_user(seam_a).channels_for_bot()["channels"], [])
        stranger = self.env["res.users"].create({
            "name": "Stranger", "login": "stranger.d248",
            "group_ids": [Command.set([self.env.ref("base.group_user").id])]})
        out = self.env["oteny.bot"].with_user(stranger).channels_for_bot()
        self.assertFalse(out["ok"])

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
        # Mintable chip requires a replay-capable bearer (dedicated or dog-food otmt_).
        self.env["ir.config_parameter"].sudo().set_param(
            "oteny.broker_token_replay_view", "otci_replay_for_chip_test")
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

    def test_replay_friendly_recording_pending(self):
        from unittest.mock import patch
        session = self._open_session(token="tokRP2")
        session.write({
            "browser_session_ids": ["steel-sess-pending"],
            "outcome": "ok",
            "duration_s": 30.0,
        })
        with patch.object(
            type(self.env["oteny.broker.client"]),
            "_broker_post",
            side_effect=UserError("refused (409): recording_pending"),
        ):
            with self.assertRaises(UserError) as err:
                session.action_replay_browser()
        self.assertIn("finalized", str(err.exception).lower())
        self.assertNotIn("Steel", str(err.exception))

    def test_replay_friendly_session_busy(self):
        from unittest.mock import patch
        session = self._open_session(token="tokBusy")
        session.write({
            "browser_session_ids": ["steel-sess-busy"],
            "outcome": "ok",
            "duration_s": 30.0,
        })
        with patch.object(
            type(self.env["oteny.broker.client"]),
            "_broker_post",
            side_effect=UserError("refused (409): session_busy"),
        ):
            with self.assertRaises(UserError) as err:
                session.action_replay_browser()
        self.assertIn("login", str(err.exception).lower())

    def test_attach_browser_sessions_mid_run_live_now(self):
        session = self._open_session(token="tokAttach")
        res = self.env["oteny.bot"].attach_browser_sessions(
            "tokAttach", ["steel-1"])
        self.assertTrue(res["ok"])
        session.invalidate_recordset()
        self.assertEqual(session.browser_session_ids, ["steel-1"])
        self.assertEqual(session.outcome, "dispatched")
        self.assertEqual(session.browser_status, "Live now")
        # Second call merges; outcome stays dispatched.
        res2 = self.env["oteny.bot"].attach_browser_sessions(
            "tokAttach", ["steel-1", "steel-2"])
        self.assertTrue(res2["ok"])
        session.invalidate_recordset()
        self.assertEqual(session.browser_session_ids, ["steel-1", "steel-2"])
        self.assertEqual(session.outcome, "dispatched")
        # After close: ids may still merge; outcome must not reopen.
        session.outcome = "ok"
        session.duration_s = 12.0
        res3 = self.env["oteny.bot"].attach_browser_sessions(
            "tokAttach", ["steel-3"])
        self.assertTrue(res3["ok"])
        session.invalidate_recordset()
        self.assertEqual(session.outcome, "ok")
        self.assertIn("steel-3", session.browser_session_ids)
        missing = self.env["oteny.bot"].attach_browser_sessions("", ["x"])
        self.assertFalse(missing["ok"])
        unknown = self.env["oteny.bot"].attach_browser_sessions("nope", ["x"])
        self.assertFalse(unknown["ok"])

    def test_browser_status_honest_without_replay_token(self):
        # Login-gate otci_ alone must NOT claim "Replay available" as mintable.
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("oteny.broker_base_url", "https://client-ingress.oteny.bot")
        icp.set_param("oteny.broker_token", "otci_login_gate_only")
        icp.search([("key", "=", "oteny.broker_token_replay_view")]).unlink()
        icp.search([("key", "=", "oteny.broker_token_live_watch")]).unlink()
        session = self._open_session(token="tokHonest")
        session.write({
            "browser_session_ids": ["steel-sess-honest"],
            "outcome": "ok",
            "duration_s": 30.0,
        })
        session.invalidate_recordset()
        self.assertTrue(session.has_browser_session)
        self.assertNotIn("Replay available", session.browser_status)
        self.assertIn("not configured", session.browser_status.lower())
        # Dedicated replay-view token → mintable chip.
        icp.set_param("oteny.broker_token_replay_view", "otci_replay_ok")
        session.invalidate_recordset()
        self.assertIn("Replay available", session.browser_status)

    def test_broker_token_prefers_dedicated_and_skips_otci_fallback(self):
        Broker = self.env["oteny.broker.client"]
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("oteny.broker_token", "otci_login_only")
        icp.search([("key", "=", "oteny.broker_token_replay_view")]).unlink()
        self.assertEqual(Broker._broker_token("login-gate"), "otci_login_only")
        self.assertFalse(Broker._broker_purpose_configured("replay-view"))
        self.assertEqual(Broker._broker_token("replay-view"), "")
        # Dog-food otmt_ still falls back for Watch/Replay.
        icp.set_param("oteny.broker_token", "otmt_dogfood")
        self.assertTrue(Broker._broker_purpose_configured("replay-view"))
        self.assertEqual(Broker._broker_token("replay-view"), "otmt_dogfood")
        icp.set_param("oteny.broker_token_replay_view", "otci_dedicated_replay")
        self.assertEqual(Broker._broker_token("replay-view"), "otci_dedicated_replay")

    def test_replay_401_maps_to_not_configured(self):
        from unittest.mock import patch
        session = self._open_session(token="tok401")
        session.write({
            "browser_session_ids": ["steel-sess-401"],
            "outcome": "ok",
            "duration_s": 30.0,
        })
        with patch.object(
            type(self.env["oteny.broker.client"]),
            "_broker_post",
            side_effect=UserError(
                "refused (401): unknown or inactive token"),
        ):
            with self.assertRaises(UserError) as err:
                session.action_replay_browser()
        msg = str(err.exception).lower()
        self.assertIn("not configured", msg)
        self.assertIn("administrator", msg)
        self.assertNotIn("401", str(err.exception))
