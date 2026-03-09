from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from datetime import date


@tagged("post_install", "-at_install", "riverflow", "test_weekend_deadline_rule")
class WeekendDeadlineRuleTestCase(TransactionCase):
    """Tests for the weekend_deadline_rule feature.

    Dispatchers don't work weekends. Services with computed deadlines
    (use_project_deadline_from != 'self') can be shifted to Friday or Monday
    when the deadline falls on a Saturday or Sunday.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Root service with deadline on a Wednesday (2026-03-18)
        # so children can be offset to land on specific weekdays
        cls.root = cls.env["riverflow.service"].create(
            {
                "name": "WDR Root",
                "project_deadline": date(2026, 3, 18),  # Wednesday
            }
        )

    def _create_child(self, days_relative, weekend_rule="allow"):
        return self.env["riverflow.service"].create(
            {
                "name": "WDR Child",
                "parent_id": self.root.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": days_relative,
                "weekend_deadline_rule": weekend_rule,
            }
        )

    # --- friday_before ---

    def test_friday_before_shifts_saturday_to_friday(self):
        """Saturday deadline with friday_before rule shifts to the preceding Friday."""
        # Root is Wed 2026-03-18, offset +3 = Saturday 2026-03-21
        child = self._create_child(3, "friday_before")
        self.assertEqual(child.deadline, date(2026, 3, 20))  # Friday

    def test_friday_before_shifts_sunday_to_friday(self):
        """Sunday deadline with friday_before rule shifts to the preceding Friday."""
        # Root is Wed 2026-03-18, offset +4 = Sunday 2026-03-22
        child = self._create_child(4, "friday_before")
        self.assertEqual(child.deadline, date(2026, 3, 20))  # Friday

    # --- monday_after ---

    def test_monday_after_shifts_saturday_to_monday(self):
        """Saturday deadline with monday_after rule shifts to the following Monday."""
        # Root is Wed 2026-03-18, offset +3 = Saturday 2026-03-21
        child = self._create_child(3, "monday_after")
        self.assertEqual(child.deadline, date(2026, 3, 23))  # Monday

    def test_monday_after_shifts_sunday_to_monday(self):
        """Sunday deadline with monday_after rule shifts to the following Monday."""
        # Root is Wed 2026-03-18, offset +4 = Sunday 2026-03-22
        child = self._create_child(4, "monday_after")
        self.assertEqual(child.deadline, date(2026, 3, 23))  # Monday

    # --- allow ---

    def test_allow_keeps_saturday(self):
        """Saturday deadline with allow rule stays on Saturday."""
        child = self._create_child(3, "allow")
        self.assertEqual(child.deadline, date(2026, 3, 21))  # Saturday

    def test_allow_keeps_sunday(self):
        """Sunday deadline with allow rule stays on Sunday."""
        child = self._create_child(4, "allow")
        self.assertEqual(child.deadline, date(2026, 3, 22))  # Sunday

    # --- weekday no-op ---

    def test_friday_before_does_not_shift_weekday(self):
        """Weekday deadlines are never shifted, regardless of rule."""
        # Root is Wed 2026-03-18, offset +2 = Friday 2026-03-20
        child = self._create_child(2, "friday_before")
        self.assertEqual(child.deadline, date(2026, 3, 20))  # Friday, unchanged

    def test_monday_after_does_not_shift_weekday(self):
        """Weekday deadlines are never shifted, regardless of rule."""
        # Root is Wed 2026-03-18, offset +0 = Wednesday 2026-03-18
        child = self._create_child(0, "monday_after")
        self.assertEqual(child.deadline, date(2026, 3, 18))  # Wednesday, unchanged

    # --- manual override bypass ---

    def test_self_mode_not_shifted_even_with_friday_rule(self):
        """Manual deadlines (use_project_deadline_from='self') are never shifted.

        The weekend rule only applies to computed deadlines where
        is_days_relative_to_project_applicable is True.
        """
        service = self.env["riverflow.service"].create(
            {
                "name": "WDR Manual",
                "use_project_deadline_from": "self",
                "project_deadline": date(2026, 3, 21),  # Saturday
                "weekend_deadline_rule": "friday_before",
            }
        )
        self.assertEqual(service.deadline, date(2026, 3, 21))  # Saturday stays

    def test_self_mode_not_shifted_even_with_monday_rule(self):
        """Manual deadlines are not shifted even with monday_after rule."""
        service = self.env["riverflow.service"].create(
            {
                "name": "WDR Manual Monday",
                "use_project_deadline_from": "self",
                "project_deadline": date(2026, 3, 22),  # Sunday
                "weekend_deadline_rule": "monday_after",
            }
        )
        self.assertEqual(service.deadline, date(2026, 3, 22))  # Sunday stays

    def test_calendar_drag_to_weekend_stays(self):
        """When a dispatcher drags a service to a weekend date via the calendar,
        _inverse_deadline switches to 'self' mode, so the weekend rule no longer applies.
        """
        child = self._create_child(-3, "friday_before")
        # Initial deadline: 2026-03-15 (Sunday) -> shifted to 2026-03-13 (Friday)
        self.assertEqual(child.deadline, date(2026, 3, 13))

        # Simulate calendar drag to Saturday 2026-03-21
        child.deadline = date(2026, 3, 21)
        self.assertEqual(child.use_project_deadline_from, "self")
        self.assertEqual(child.deadline, date(2026, 3, 21))  # Saturday stays

    # --- recomputation on rule change ---

    def test_changing_rule_recomputes_deadline(self):
        """Changing weekend_deadline_rule triggers deadline recomputation."""
        child = self._create_child(3, "allow")
        self.assertEqual(child.deadline, date(2026, 3, 21))  # Saturday

        child.weekend_deadline_rule = "friday_before"
        self.assertEqual(child.deadline, date(2026, 3, 20))  # Friday

        child.weekend_deadline_rule = "monday_after"
        self.assertEqual(child.deadline, date(2026, 3, 23))  # Monday

        child.weekend_deadline_rule = "allow"
        self.assertEqual(child.deadline, date(2026, 3, 21))  # Saturday again

    # --- recomputation on project_deadline change ---

    def test_root_deadline_change_reapplies_weekend_rule(self):
        """When the root's deadline changes, the child's deadline is recomputed
        with the weekend rule applied to the new date.
        """
        child = self._create_child(3, "friday_before")
        # Root Wed 2026-03-18 + 3 = Sat 2026-03-21 -> Fri 2026-03-20
        self.assertEqual(child.deadline, date(2026, 3, 20))

        # Move root to Thursday 2026-03-19; +3 = Sun 2026-03-22 -> Fri 2026-03-20
        self.root.project_deadline = date(2026, 3, 19)
        self.assertEqual(child.deadline, date(2026, 3, 20))

        # Move root to Friday 2026-03-20; +3 = Mon 2026-03-23 (weekday, no shift)
        self.root.project_deadline = date(2026, 3, 20)
        self.assertEqual(child.deadline, date(2026, 3, 23))

    # --- template creation inheritance ---

    def test_template_creation_copies_weekend_rule(self):
        """weekend_deadline_rule is copied from template to new service."""
        Service = self.env["riverflow.service"]

        template = Service.create(
            {
                "name": "Template Root",
                "is_this_a_template": True,
                "project_deadline": date(2026, 1, 1),
                "weekend_deadline_rule": "friday_before",
            }
        )
        template_child = Service.create(
            {
                "name": "Template Child",
                "parent_id": template.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -3,
                "weekend_deadline_rule": "monday_after",
            }
        )

        # Create services from the template
        new_services = Service.with_context(
            default_res_model="riverflow.service",
            default_res_id=0,
        )._create_services_from_template(template.id, project_deadline=date(2026, 6, 15))

        new_root = new_services[0]
        self.assertEqual(
            new_root.weekend_deadline_rule,
            "friday_before",
            "Root service should inherit friday_before from template",
        )

        new_child = new_root.child_ids
        self.assertEqual(len(new_child), 1)
        self.assertEqual(
            new_child.weekend_deadline_rule,
            "monday_after",
            "Child service should inherit monday_after from template",
        )

    # --- default value ---

    def test_default_is_allow(self):
        """New services default to 'allow' weekend rule."""
        service = self.env["riverflow.service"].create(
            {
                "name": "WDR Default",
                "project_deadline": date(2026, 3, 18),
            }
        )
        self.assertEqual(service.weekend_deadline_rule, "allow")
