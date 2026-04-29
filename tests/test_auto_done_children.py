from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_auto_done_children")
class TestAutoDoneChildrenOnEnter(TransactionCase):
    """Test the auto_done_children_on_enter mechanism on riverflow.state.

    When a service transitions into a state flagged with
    auto_done_children_on_enter=True, all active non-end-state children
    are moved to the first non-cancelled end state (by sequence) of
    their own workflow. Mirror of auto_progress_on_children_done in the
    opposite direction.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")

        # -- Parent workflow: 3 visible states, the 'Done' state has the flag --
        cls.parent_workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Cascade Parent WF",
        })
        cls.parent_not_started = State.create({
            "workflow_id": cls.parent_workflow.id,
            "name": "Not Started",
            "sequence": 10,
        })
        cls.parent_in_progress = State.create({
            "workflow_id": cls.parent_workflow.id,
            "name": "In Progress",
            "sequence": 20,
        })
        cls.parent_done = State.create({
            "workflow_id": cls.parent_workflow.id,
            "name": "Done",
            "sequence": 30,
            "is_end_state": True,
            "auto_done_children_on_enter": True,
        })
        cls.parent_not_needed = State.create({
            "workflow_id": cls.parent_workflow.id,
            "name": "Not Needed",
            "sequence": 40,
            "is_end_state": True,
        })
        cls.parent_cancelled = State.create({
            "workflow_id": cls.parent_workflow.id,
            "name": "Cancelled",
            "sequence": 50,
            "is_end_state": True,
            "is_cancelled_state": True,
            "hide_in_statusbar": True,
        })

        cls.trans_parent_initial = Transition.create({
            "name": "Start",
            "to_state_id": cls.parent_not_started.id,
            "action_id": default_action.id,
            "sequence": 10,
        })
        cls.trans_parent_to_done = Transition.create({
            "name": "Mark Done",
            "from_state_id": cls.parent_not_started.id,
            "to_state_id": cls.parent_done.id,
            "action_id": default_action.id,
            "sequence": 10,
        })
        cls.trans_parent_to_not_needed = Transition.create({
            "name": "Not Needed",
            "from_state_id": cls.parent_not_started.id,
            "to_state_id": cls.parent_not_needed.id,
            "action_id": default_action.id,
            "sequence": 20,
        })
        cls.trans_parent_to_cancelled = Transition.create({
            "name": "Cancel",
            "from_state_id": cls.parent_not_started.id,
            "to_state_id": cls.parent_cancelled.id,
            "action_id": default_action.id,
            "sequence": 30,
        })

        # -- Child workflow: Not Started -> Done (first end state) -> Not Needed -> Cancelled --
        # The cascade should pick Done (first non-cancelled end state by sequence).
        cls.child_workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Cascade Child WF",
        })
        cls.child_not_started = State.create({
            "workflow_id": cls.child_workflow.id,
            "name": "Not Started",
            "sequence": 10,
        })
        cls.child_done = State.create({
            "workflow_id": cls.child_workflow.id,
            "name": "Done",
            "sequence": 20,
            "is_end_state": True,
        })
        cls.child_not_needed = State.create({
            "workflow_id": cls.child_workflow.id,
            "name": "Not Needed",
            "sequence": 30,
            "is_end_state": True,
        })
        cls.child_cancelled = State.create({
            "workflow_id": cls.child_workflow.id,
            "name": "Cancelled",
            "sequence": 40,
            "is_end_state": True,
            "is_cancelled_state": True,
        })

        cls.trans_child_initial = Transition.create({
            "name": "Start",
            "to_state_id": cls.child_not_started.id,
            "action_id": default_action.id,
            "sequence": 10,
        })

    def _transition_service(self, service, transition):
        """Simulate a transition via the service wizard."""
        wizard = (
            self.env["riverflow.service.wizard"]
            .with_context(
                active_model="riverflow.service",
                active_ids=[service.id],
                transition_id=transition.id,
            )
            .create({})
        )
        wizard.action_save()

    def _create_parent_with_children(self, child_count=2):
        Service = self.env["riverflow.service"]
        parent = Service.create({
            "name": "Cascade Parent",
            "workflow_id": self.parent_workflow.id,
            "state_id": self.parent_not_started.id,
        })
        children = Service.browse()
        for i in range(child_count):
            child = Service.create({
                "name": f"Cascade Child {i + 1}",
                "parent_id": parent.id,
                "workflow_id": self.child_workflow.id,
                "state_id": self.child_not_started.id,
            })
            children += child
        return parent, children

    def test_cascade_done_to_active_children(self):
        """Parent entering cascade state moves active children to Done."""
        parent, children = self._create_parent_with_children(2)
        self.assertTrue(all(c.state_id == self.child_not_started for c in children))

        self._transition_service(parent, self.trans_parent_to_done)

        self.assertEqual(parent.state_id, self.parent_done)
        for child in children:
            self.assertEqual(
                child.state_id,
                self.child_done,
                "Cascade should pick the first non-cancelled end state by sequence",
            )

    def test_no_cascade_when_flag_not_set(self):
        """Entering a non-flagged end state does NOT cascade."""
        parent, children = self._create_parent_with_children(2)
        self._transition_service(parent, self.trans_parent_to_not_needed)
        self.assertEqual(parent.state_id, self.parent_not_needed)
        # Children untouched
        for child in children:
            self.assertEqual(child.state_id, self.child_not_started)

    def test_no_cascade_for_cancelled_state(self):
        """Cancelled (separate end state) does not cascade either."""
        parent, children = self._create_parent_with_children(1)
        self._transition_service(parent, self.trans_parent_to_cancelled)
        self.assertEqual(parent.state_id, self.parent_cancelled)
        self.assertEqual(children[0].state_id, self.child_not_started)

    def test_children_already_in_end_state_untouched(self):
        """Children already in an end state (Done/Cancelled/Not Needed) are skipped."""
        parent, children = self._create_parent_with_children(3)
        children[0].state_id = self.child_done
        children[1].state_id = self.child_cancelled
        children[2].state_id = self.child_not_needed
        # All in end states already.
        self._transition_service(parent, self.trans_parent_to_done)
        self.assertEqual(children[0].state_id, self.child_done)
        self.assertEqual(children[1].state_id, self.child_cancelled)
        self.assertEqual(children[2].state_id, self.child_not_needed)

    def test_inactive_children_skipped(self):
        """Inactive (archived) children are not cascaded to Done."""
        parent, children = self._create_parent_with_children(2)
        children[0].active = False
        self._transition_service(parent, self.trans_parent_to_done)
        self.assertEqual(
            children[0].state_id,
            self.child_not_started,
            "Inactive child should not be cascaded",
        )
        self.assertEqual(children[1].state_id, self.child_done)

    def test_parent_with_no_children_is_noop(self):
        """Parent flagged but with no children is a no-op."""
        Service = self.env["riverflow.service"]
        parent = Service.create({
            "name": "Childless Cascade Parent",
            "workflow_id": self.parent_workflow.id,
            "state_id": self.parent_not_started.id,
        })
        self._transition_service(parent, self.trans_parent_to_done)
        self.assertEqual(parent.state_id, self.parent_done)

    def test_cascade_ignores_cancelled_end_state_when_picking_done(self):
        """Picks 'Done' (sequence 20), not 'Cancelled' (sequence 40, is_cancelled_state)."""
        parent, children = self._create_parent_with_children(1)
        self._transition_service(parent, self.trans_parent_to_done)
        self.assertEqual(children[0].state_id, self.child_done)
        self.assertNotEqual(children[0].state_id, self.child_cancelled)

    def test_direct_method_call(self):
        """Direct _cascade_done_to_children call also works (covers programmatic use)."""
        parent, children = self._create_parent_with_children(1)
        # Directly write state without going through the wizard
        parent.state_id = self.parent_done
        # Manually invoke the cascade as the wizard would
        parent._cascade_done_to_children()
        self.assertEqual(children[0].state_id, self.child_done)
