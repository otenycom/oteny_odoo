"""Generic one-live-slot drain: leave a slot-holding state, dispatch the oldest queued peer."""

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_bot_one_live_slot")
class TestBotOneLiveSlotDrain(TransactionCase):
    """The mixin drain hook has no Cuneus names. It only walks the same workflow."""

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
            "name": "Test One Live Slot WF",
        })
        cls.state_queue = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Queued",
            "sequence": 10,
            "bot_stage": "queue",
        })
        cls.state_run = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Running",
            "sequence": 20,
            "bot_stage": "in_progress",
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
        Transition.create({
            "name": "Finish",
            "from_state_id": cls.state_run.id,
            "to_state_id": cls.state_done.id,
            "action_id": default_action.id,
            "bot_role": "work",
            "sequence": 10,
        })
        cls.Service = Service

    def _make(self, name, state):
        return self.Service.with_context(bot_no_inline_dispatch=True).create({
            "name": name,
            "workflow_id": self.workflow.id,
            "state_id": state.id,
        })

    def test_leaving_in_progress_dispatches_oldest_queued_peer(self):
        occupant = self._make("SlotA", self.state_run)
        older = self._make("SlotB", self.state_queue)
        newer = self._make("SlotC", self.state_queue)
        self.assertLess(older.id, newer.id)
        dispatched = []

        def _dispatch(svc):
            dispatched.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_dispatch_one", _dispatch):
            occupant.with_context(bot_no_inline_dispatch=False).state_id = (
                self.state_done
            )
        self.assertEqual(dispatched, [older.id])
        self.assertEqual(occupant.state_id, self.state_done)

    def test_no_inline_context_skips_drain(self):
        occupant = self._make("SkipA", self.state_run)
        self._make("SkipB", self.state_queue)
        dispatched = []

        def _dispatch(svc):
            dispatched.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_dispatch_one", _dispatch):
            occupant.with_context(bot_no_inline_dispatch=True).state_id = (
                self.state_done
            )
        self.assertEqual(dispatched, [])
