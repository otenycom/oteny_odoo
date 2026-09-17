"""riverflow answers the bridge's work contract: consume once, probe tells an expected
end from a lost claim, release hands the record back through the timeout exit."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_work_contract")
class TestWorkContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        State = cls.env["riverflow.state"]; Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")
        cls.workflow = Workflow.create({"model_id": service_model.id, "name": "Contract WF"})
        cls.state_queue = State.create({"workflow_id": cls.workflow.id, "name": "Queued", "sequence": 10,
                                        "bot_stage": "queue", "is_owned_by_bot": True})
        cls.state_run = State.create({"workflow_id": cls.workflow.id, "name": "Running", "sequence": 20,
                                      "bot_stage": "in_progress", "is_owned_by_bot": True, "bot_timeout_minutes": 30})
        cls.state_run_no_exit = State.create({"workflow_id": cls.workflow.id, "name": "Running (no exit)", "sequence": 25,
                                              "bot_stage": "in_progress", "is_owned_by_bot": True})
        cls.state_done = State.create({"workflow_id": cls.workflow.id, "name": "Done", "sequence": 30, "is_end_state": True})
        cls.state_back = State.create({"workflow_id": cls.workflow.id, "name": "Handed back", "sequence": 40})
        cls.t_claim = Transition.create({"name": "Claim", "from_state_id": cls.state_queue.id, "to_state_id": cls.state_run.id,
                                         "action_id": default_action.id, "bot_role": "claim", "sequence": 10})
        cls.t_claim_no_exit = Transition.create({"name": "Claim (no exit)", "from_state_id": cls.state_queue.id,
                                                 "to_state_id": cls.state_run_no_exit.id, "action_id": default_action.id,
                                                 "bot_role": "claim", "sequence": 20})
        cls.t_work = Transition.create({"name": "Mark done", "from_state_id": cls.state_run.id, "to_state_id": cls.state_done.id,
                                        "action_id": default_action.id, "bot_role": "work", "sequence": 10})
        cls.t_timeout = Transition.create({"name": "Hand back", "from_state_id": cls.state_run.id, "to_state_id": cls.state_back.id,
                                           "action_id": default_action.id, "bot_role": "escalate", "is_bot_timeout": True, "sequence": 20})
        cls.bot = cls.env["oteny.bot"].create({"name": "Contract Bot", "bot_user_id": cls.env.uid})

    def _claimed(self, name="Contract service", claim=None):
        Service = self.env["riverflow.service"].with_context(bot_no_inline_dispatch=True)
        service = Service.create({"name": name, "workflow_id": self.workflow.id, "state_id": self.state_queue.id,
                                  "company_id": self.env.company.id})
        out = self.env["riverflow.service"].bot_claim(service.id, (claim or self.t_claim).id)
        self.assertTrue(out["ok"], out); token = out["token"]
        self.env["oteny.bot.session"].create({
            "bot_id": self.bot.id, "name": name, "kind": "isolated_turn", "outcome": "dispatched",
            "work_token": token, "origin_model": "riverflow.service", "origin_res_id": service.id})
        return service, token

    def test_consume_is_once_per_dispatch(self):
        _service, token = self._claimed()
        Bot = self.env["oteny.bot"]
        self.assertTrue(Bot.work_consume(token)["ok"])
        second = Bot.work_consume(token)
        self.assertFalse(second["ok"]); self.assertEqual(second["reason"], "run already consumed")

    def test_probe_is_mine_while_live_and_released_after_the_turns_own_advance(self):
        service, token = self._claimed()
        Bot = self.env["oteny.bot"]
        probe = Bot.work_probe(token)
        self.assertTrue(probe["ok"]); self.assertTrue(probe["mine"]); self.assertFalse(probe["released"])
        done = self.env["riverflow.service"].bot_claim(service.id, self.t_work.id, work_token=token)
        self.assertTrue(done["ok"])
        probe = Bot.work_probe(token)
        self.assertTrue(probe["ok"]); self.assertFalse(probe["mine"]); self.assertTrue(probe["released"])
        self.assertEqual(probe["state"], "Done")

    def test_probe_reports_a_lost_claim(self):
        service, token = self._claimed()
        # The reaper (or a person) takes the record with the live token: not the turn's own advance.
        self.env["riverflow.service"].with_context(bot_reap=True).bot_claim(
            service.id, self.t_timeout.id, work_token=service.bot_claim_token)
        service.bot_released_token = False  # a take that was not this turn's advance
        probe = self.env["oteny.bot"].work_probe(token)
        self.assertTrue(probe["ok"]); self.assertFalse(probe["mine"]); self.assertFalse(probe["released"])
        self.assertEqual(probe["reason"], "not in progress")

    def test_release_hands_the_record_back_through_the_timeout_exit(self):
        service, token = self._claimed()
        out = self.env["oteny.bot"].work_release(token, reason="model stream hung",
                                                 run={"outcome": "error", "outcome_detail": "model stream hung"})
        self.assertTrue(out["ok"]); self.assertTrue(out["released"]); self.assertEqual(out["state"], "Handed back")
        self.assertEqual(service.state_id, self.state_back)
        session = self.env["oteny.bot.session"].search([("work_token", "=", token)], limit=1)
        self.assertEqual(session.outcome, "error")
        again = self.env["oteny.bot"].work_release(token, reason="again")
        self.assertTrue(again["ok"]); self.assertFalse(again["released"])

    def test_release_without_a_timeout_exit_leaves_the_record_and_says_so(self):
        service, token = self._claimed(name="No exit", claim=self.t_claim_no_exit)
        out = self.env["oteny.bot"].work_release(token, reason="hung")
        self.assertTrue(out["ok"]); self.assertFalse(out["released"]); self.assertIn("no timeout exit", out["reason"])
        self.assertEqual(service.state_id, self.state_run_no_exit)
