"""HR never sees claim/work. Live claim shows a working note. Queue has no primary."""

from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_transition_buttons_bot_hide")
class TestTransitionButtonsBotHide(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Service = cls.env["riverflow.service"]
        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")

        cls.workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Bot Hide WF",
        })
        cls.state_queue = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Queued",
            "sequence": 10,
            "bot_stage": "queue",
            "is_owned_by_bot": True,
            "bot_timeout_minutes": 15,
        })
        cls.state_run = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Running",
            "sequence": 20,
            "bot_stage": "in_progress",
            "is_owned_by_bot": True,
            "bot_timeout_minutes": 30,
        })
        cls.state_done = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Done",
            "sequence": 30,
            "is_end_state": True,
        })
        Transition.create({
            "name": "Claim",
            "from_state_id": cls.state_queue.id,
            "to_state_id": cls.state_run.id,
            "action_id": default_action.id,
            "bot_role": "claim",
            "sequence": 10,
        })
        cls.trans_stop = Transition.create({
            "name": "Stop and return",
            "from_state_id": cls.state_queue.id,
            "to_state_id": cls.state_done.id,
            "action_id": default_action.id,
            "sequence": 20,
            "is_bot_timeout": True,
        })
        Transition.create({
            "name": "Finish",
            "from_state_id": cls.state_run.id,
            "to_state_id": cls.state_done.id,
            "action_id": default_action.id,
            "bot_role": "work",
            "sequence": 10,
        })
        cls.trans_run_stop = Transition.create({
            "name": "Stop and return",
            "from_state_id": cls.state_run.id,
            "to_state_id": cls.state_done.id,
            "action_id": default_action.id,
            "sequence": 20,
            "is_bot_timeout": True,
        })
        cls.Service = Service

    def _make(self, name, state):
        return self.Service.with_context(bot_no_inline_dispatch=True).create({
            "name": name,
            "workflow_id": self.workflow.id,
            "state_id": state.id,
        })

    def test_hr_does_not_see_claim_or_work(self):
        rec = self._make("HideA", self.state_queue)
        captions = [b["caption"] for b in rec.transition_buttons_json["buttons"]]
        self.assertEqual(captions, ["Stop and return"])
        self.assertFalse(rec.transition_buttons_json["buttons"][0]["primary"])

    def test_queue_has_no_primary(self):
        rec = self._make("NoPrimary", self.state_queue)
        self.assertTrue(all(
            not b["primary"] for b in rec.transition_buttons_json["buttons"]
        ))

    def test_live_claim_shows_the_note_and_only_the_abort(self):
        """A live run hides every exit but one. The note says the bot is working and names
        the hour it is handed back, and the state's own timeout exit sits under it — the
        same door the reaper takes on the clock, offered to whoever can see the run is dead.
        Any other exit would only raise from the fence, so a button for it is worse than
        none."""
        rec = self._make("Live", self.state_run)
        rec.bot_run_started_at = fields.Datetime.now()
        rec.invalidate_recordset(["transition_buttons_json"])
        payload = rec.transition_buttons_json
        self.assertEqual([b["caption"] for b in payload["buttons"]],
                         [self.trans_run_stop.name])
        self.assertEqual(payload["buttons"][0]["context"]["transition_id"],
                         self.trans_run_stop.id)
        self.assertFalse(payload["buttons"][0]["primary"], "an abort is never the default")
        self.assertIn("working", (payload.get("working_note") or "").lower())

    def test_a_live_claim_with_no_declared_timeout_exit_shows_no_buttons(self):
        """The abort is driven by the workflow's own declaration, not by a hard-coded name.
        A state that declares no timeout exit has no hand-back to offer, and the panel is
        back to the note alone."""
        rec = self._make("LiveNoExit", self.state_run)
        rec.bot_run_started_at = fields.Datetime.now()
        self.trans_run_stop.is_bot_timeout = False
        rec.invalidate_recordset(["transition_buttons_json"])
        payload = rec.transition_buttons_json
        self.assertEqual(payload["buttons"], [])
        self.assertIn("working", (payload.get("working_note") or "").lower())

    def test_working_note_uses_user_timezone(self):
        rec = self._make("TzNote", self.state_run)
        rec.bot_work_started_at = datetime(2026, 8, 29, 19, 4, 33)
        self.env.user.tz = "UTC"
        utc_note = rec.with_context(tz="UTC")._bot_working_note()
        self.assertIn("2026-08-29 19:04:33", utc_note)
        self.assertIn("2026-08-29 19:34:33", utc_note)
        self.env.user.tz = "Europe/Amsterdam"
        ams_note = rec.with_context(tz="Europe/Amsterdam")._bot_working_note()
        self.assertIn("2026-08-29 21:04:33", ams_note)
        self.assertIn("2026-08-29 21:34:33", ams_note)
        self.assertNotIn("2026-08-29 19:04:33", ams_note)

    def test_queue_with_sla_stamps_the_clock(self):
        rec = self._make("SlaQ", self.state_queue)
        self.assertTrue(rec.bot_work_started_at)
        self.assertFalse(rec.bot_claim_token)

    def test_queue_sla_reaper_uses_stop(self):
        rec = self._make("ReapQ", self.state_queue)
        rec.bot_work_started_at = fields.Datetime.now() - timedelta(minutes=20)
        n = self.Service._bot_reap_timeouts()
        self.assertGreaterEqual(n, 1)
        self.assertEqual(rec.state_id, self.state_done)
