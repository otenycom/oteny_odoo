"""Generic one-live-slot drain: leave a slot-holding state, dispatch the oldest queued peer."""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
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

    def test_sla_less_login_hold_does_not_occupy_the_slot(self):
        """A human park with no clock must not freeze a sibling queue."""
        hold = self.env["riverflow.state"].create({
            "workflow_id": self.workflow.id,
            "name": "Parked Login",
            "sequence": 15,
            "bot_login_hold": True,
        })
        self._make("Parked", hold)
        queued = self._make("Fresh", self.state_queue)
        self.assertFalse(queued._bot_one_live_slot_defers())
        self.assertFalse(queued._bot_one_live_slot_occupant())

    def test_login_hold_with_sla_occupies_the_slot(self):
        hold = self.env["riverflow.state"].create({
            "workflow_id": self.workflow.id,
            "name": "Resume Queue",
            "sequence": 16,
            "bot_stage": "queue",
            "bot_login_hold": True,
            "bot_timeout_minutes": 15,
        })
        parked = self._make("Resume", hold)
        queued = self._make("FreshB", self.state_queue)
        self.assertTrue(queued._bot_one_live_slot_defers())
        self.assertEqual(queued._bot_one_live_slot_occupant(), parked)

    def _park_state(self, name, **extra):
        vals = {
            "workflow_id": self.workflow.id,
            "name": name,
            "sequence": 17,
            "bot_login_hold": True,
        }
        vals.update(extra)
        return self.env["riverflow.state"].create(vals)

    def test_leaving_in_progress_resumes_fresh_login_park(self):
        hold = self._park_state("Parked Login Fresh")
        occupant = self._make("RunPark", self.state_run)
        park = self._make("ParkFresh", hold)
        resumed = []

        def _resume(svc):
            resumed.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_resume_login_park", _resume):
            occupant.with_context(bot_no_inline_dispatch=False).state_id = (
                self.state_done
            )
        self.assertEqual(resumed, [park.id])

    def test_queue_peer_wins_over_login_park(self):
        hold = self._park_state("Parked Behind Queue")
        occupant = self._make("RunQ", self.state_run)
        self._make("ParkBehind", hold)
        queued = self._make("QueuedWins", self.state_queue)
        dispatched = []
        resumed = []

        def _dispatch(svc):
            dispatched.append(svc.id)
            return True

        def _resume(svc):
            resumed.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_dispatch_one", _dispatch), \
                patch.object(type(self.Service), "_bot_resume_login_park", _resume):
            occupant.with_context(bot_no_inline_dispatch=False).state_id = (
                self.state_done
            )
        self.assertEqual(dispatched, [queued.id])
        self.assertEqual(resumed, [])

    def test_stale_login_park_is_not_resumed(self):
        hold = self._park_state("Parked Login Stale")
        occupant = self._make("RunStale", self.state_run)
        self._make("ParkStale", hold)
        resumed = []
        future = fields.Datetime.now() + timedelta(hours=1)

        def _resume(svc):
            resumed.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_resume_login_park", _resume), \
                patch.object(
                    type(self.Service), "_bot_login_park_since",
                    return_value=future,
                ):
            occupant.with_context(bot_no_inline_dispatch=False).state_id = (
                self.state_done
            )
        self.assertEqual(resumed, [])

    def test_occupying_login_hold_is_dispatched_not_resumed(self):
        hold = self._park_state(
            "Resume Queue SLA",
            bot_stage="queue",
            bot_timeout_minutes=15,
        )
        occupant = self._make("RunOcc", self.state_run)
        parked = self._make("ResumeSLA", hold)
        dispatched = []
        resumed = []

        def _dispatch(svc):
            dispatched.append(svc.id)
            return True

        def _resume(svc):
            resumed.append(svc.id)
            return True

        with patch.object(type(self.Service), "_bot_dispatch_one", _dispatch), \
                patch.object(type(self.Service), "_bot_resume_login_park", _resume):
            occupant.with_context(bot_no_inline_dispatch=False).state_id = (
                self.state_done
            )
        self.assertEqual(dispatched, [parked.id])
        self.assertEqual(resumed, [])

    def test_occupant_of_workflow_empty(self):
        occ = self.Service._bot_one_live_slot_occupant_of_workflow(self.workflow)
        self.assertFalse(occ)
        queued = self.Service._bot_one_live_slot_queued_of_workflow(self.workflow)
        self.assertFalse(queued)

    def test_occupant_of_workflow_sla_less_park_is_not_occupant(self):
        hold = self._park_state("Parked Login UI")
        self._make("ParkUI", hold)
        occ = self.Service._bot_one_live_slot_occupant_of_workflow(self.workflow)
        self.assertFalse(occ)

    def test_occupant_of_workflow_sla_login_hold_is_occupant(self):
        hold = self._park_state(
            "Resume Queue UI",
            bot_stage="queue",
            bot_timeout_minutes=15,
        )
        parked = self._make("ResumeUI", hold)
        occ = self.Service._bot_one_live_slot_occupant_of_workflow(self.workflow)
        self.assertEqual(occ, parked)

    def test_occupant_of_workflow_claimed_in_progress_is_occupant(self):
        claimed = self._make("ClaimedUI", self.state_run)
        occ = self.Service._bot_one_live_slot_occupant_of_workflow(self.workflow)
        self.assertEqual(occ, claimed)

    def test_queued_of_workflow_excludes_occupant(self):
        hold = self._park_state(
            "Resume Queue Count",
            bot_stage="queue",
            bot_timeout_minutes=15,
        )
        occupant = self._make("OccQueue", hold)
        waiting = self._make("WaitQueue", self.state_queue)
        queued = self.Service._bot_one_live_slot_queued_of_workflow(
            self.workflow, occupant
        )
        self.assertEqual(queued, waiting)
        self.assertNotIn(occupant, queued)
