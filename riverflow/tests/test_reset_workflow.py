from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_reset_workflow")
class TestResetWorkflowToXml(TransactionCase):
    """Test reset_workflow_to_xml restores workflow definitions from XML data files.

    Uses the Task workflow (riverflow.workflow_service_task) which is defined
    in riverflow/data/workflow_service_task.xml with known states and transitions.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task_workflow = cls.env.ref("riverflow.workflow_service_task")
        cls.state_not_started = cls.env.ref("riverflow.state_task_not_started")
        cls.state_in_progress = cls.env.ref("riverflow.state_task_in_progress")
        cls.state_done = cls.env.ref("riverflow.state_task_done")

    def test_reset_restores_modified_fields(self):
        """Field values changed via UI are restored to XML-defined values."""
        self.state_not_started.name = "MODIFIED NAME"
        self.state_not_started.sequence = 999
        self.state_not_started.color_int = 0
        self.assertEqual(self.state_not_started.name, "MODIFIED NAME")

        self.task_workflow.reset_workflow_to_xml()

        self.state_not_started.invalidate_recordset()
        self.assertEqual(self.state_not_started.name, "Not started")
        self.assertEqual(self.state_not_started.sequence, 10)
        self.assertEqual(self.state_not_started.color_int, 9)

    def test_reset_restores_modified_transitions(self):
        """Transition fields changed via UI are restored."""
        trans = self.env.ref("riverflow.trans_task_not_started_to_in_progress")
        trans.name = "MODIFIED TRANSITION"
        trans.icon = "fa-bomb"

        self.task_workflow.reset_workflow_to_xml()

        trans.invalidate_recordset()
        self.assertEqual(trans.name, "Start Progress")
        self.assertEqual(trans.icon, "fa-play")

    def test_reset_archives_manually_added_state(self):
        """States added via UI (no XML ID) are archived after reset."""
        manual_state = self.env["riverflow.state"].create(
            {
                "workflow_id": self.task_workflow.id,
                "name": "Manual State",
                "sequence": 100,
            }
        )
        self.assertTrue(manual_state.active)

        self.task_workflow.reset_workflow_to_xml()

        manual_state.invalidate_recordset()
        self.assertFalse(manual_state.active)

    def test_reset_archives_manually_added_transition(self):
        """Transitions added via UI (no XML ID) are archived after reset."""
        manual_transition = self.env["riverflow.transition"].create(
            {
                "name": "Manual Transition",
                "from_state_id": self.state_not_started.id,
                "to_state_id": self.state_done.id,
            }
        )
        self.assertTrue(manual_transition.active)

        self.task_workflow.reset_workflow_to_xml()

        manual_transition.invalidate_recordset()
        self.assertFalse(manual_transition.active)

    def test_reset_reactivates_manually_archived_state(self):
        """XML-defined states that were manually archived are re-activated."""
        self.state_in_progress.active = False

        self.task_workflow.reset_workflow_to_xml()

        self.state_in_progress.invalidate_recordset()
        self.assertTrue(self.state_in_progress.active)

    def test_reset_raises_for_workflow_without_xml_id(self):
        """Workflows created via UI (no XML ID) cannot be reset."""
        service_model = self.env["ir.model"]._get("riverflow.service")
        manual_workflow = self.env["riverflow.workflow"].create(
            {
                "model_id": service_model.id,
                "name": "Manual Workflow",
            }
        )
        with self.assertRaises(UserError):
            manual_workflow.reset_workflow_to_xml()
