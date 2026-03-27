from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged("post_install", "-at_install", "riverflow", "test_supply_time")
class TestSupplyTimeOfDay(TransactionCase):
    """Tests for the supply_time_of_day field and has_supply_time workflow flag.

    The supply_time_of_day field records the time of day for services such as
    appointment times (AB), taxi pickup times, and train departure times. The
    has_supply_time flag on the workflow controls visibility on the Supply Order tab.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.taxi_workflow = cls.env.ref("riverflow.workflow_service_taxi_order")
        cls.train_workflow = cls.env.ref("riverflow.workflow_service_train_ticket")
        cls.task_workflow = cls.env.ref("riverflow.workflow_service_task")

    def test_taxi_workflow_has_supply_time(self):
        """Taxi Order workflow has has_supply_time enabled for pickup times."""
        self.assertTrue(self.taxi_workflow.has_supply_time)

    def test_train_workflow_has_supply_time(self):
        """Train Ticket workflow has has_supply_time enabled for departure times."""
        self.assertTrue(self.train_workflow.has_supply_time)

    def test_task_workflow_no_supply_time(self):
        """Task workflow does not have has_supply_time (generic tasks have no time)."""
        self.assertFalse(self.task_workflow.has_supply_time)

    def test_supply_time_propagates_to_service(self):
        """The has_supply_time flag propagates from workflow to service via related field."""
        taxi_state = self.env["riverflow.state"].search(
            [("workflow_id", "=", self.taxi_workflow.id)], limit=1
        )
        service = self.env["riverflow.service"].create({
            "name": "Test Taxi",
            "workflow_id": self.taxi_workflow.id,
            "state_id": taxi_state.id,
        })
        self.assertTrue(service.has_supply_time)

    def test_supply_time_of_day_accepts_valid_time(self):
        """A valid time of day (10:30 = 10.5) can be set on a service."""
        service = self.env["riverflow.service"].create({
            "name": "Test Service",
            "supply_time_of_day": 10.5,
        })
        self.assertEqual(service.supply_time_of_day, 10.5)

    def test_supply_time_of_day_zero_means_not_set(self):
        """Float 0.0 is the default and means 'time not set'."""
        service = self.env["riverflow.service"].create({
            "name": "Test Service",
        })
        self.assertFalse(service.supply_time_of_day)

    def test_supply_time_constraint_rejects_negative(self):
        """Negative time values are rejected by the constraint."""
        with self.assertRaises(ValidationError):
            self.env["riverflow.service"].create({
                "name": "Test Service",
                "supply_time_of_day": -1.0,
            })

    def test_supply_time_constraint_rejects_over_24(self):
        """Time values >= 24.0 are rejected by the constraint."""
        with self.assertRaises(ValidationError):
            self.env["riverflow.service"].create({
                "name": "Test Service",
                "supply_time_of_day": 24.0,
            })

    def test_supply_time_constraint_allows_23_59(self):
        """23:59 (23.98 as float) is within the valid range."""
        service = self.env["riverflow.service"].create({
            "name": "Test Service",
            "supply_time_of_day": 23.98,
        })
        self.assertAlmostEqual(service.supply_time_of_day, 23.98, places=2)
