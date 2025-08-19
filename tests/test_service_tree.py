from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from datetime import date
from odoo.exceptions import UserError

# Testcases generated with the help of Cursor AI


@tagged("rivermen", "post_install", "-at_install", "riverflow", "test_services")
class ServiceDeadlineTestCase(TransactionCase):

    TEST_PREFIX = "TestRun "

    @classmethod
    def setUpClass(cls):
        super(ServiceDeadlineTestCase, cls).setUpClass()

    def cleanup_test_services(self):
        self.env["riverflow.service"].search([("name", "like", f"{self.TEST_PREFIX}%")]).unlink()

    def dump_services_to_console(self, services):
        print("| indented_name              | deadline   | daily_prio |")
        print("|----------------------------|------------|------------|")
        for service in services:
            print(
                f"| {service.indented_name.replace(self.TEST_PREFIX, ''):<26} | {service.deadline} | {service.daily_prio:03d} |"
            )

    def create_service_tree(self):
        self.cleanup_test_services()

        # Create 3 root services
        root_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Root Service 1",
                "project_deadline": "2024-01-01",
            }
        )

        root_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Root Service 2",
                "project_deadline": "2024-02-01",
            }
        )

        root_3 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Root Service 3",
                "project_deadline": "2024-03-01",
            }
        )

        # Create children for Root Service 2
        child_2_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 2.1",
                "parent_id": root_2.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -1,
            }
        )

        child_2_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 2.2",
                "parent_id": root_2.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -2,
            }
        )

        child_2_3 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 2.3",
                "parent_id": root_2.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -3,
            }
        )

        # Create children for Root Service 3
        child_3_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 3.1",
                "parent_id": root_3.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -1,
            }
        )

        child_3_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 3.2",
                "parent_id": root_3.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -2,
            }
        )

        child_3_3 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child 3.3",
                "parent_id": root_3.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": -3,
            }
        )

        # Create grandchildren for Child 3.2
        grandchild_3_2_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Grandchild 3.2.1",
                "parent_id": child_3_2.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": 1,
            }
        )

        grandchild_3_2_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Grandchild 3.2.2",
                "parent_id": child_3_2.id,
                "use_project_deadline_from": "root",
                "days_relative_to_project": 2,
            }
        )

        return (
            root_1,
            root_2,
            root_3,
            child_2_1,
            child_2_2,
            child_2_3,
            child_3_1,
            child_3_2,
            child_3_3,
            grandchild_3_2_1,
            grandchild_3_2_2,
        )

    def test_service_tree_deadlines(self):
        (
            root_1,
            root_2,
            root_3,
            child_2_1,
            child_2_2,
            child_2_3,
            child_3_1,
            child_3_2,
            child_3_3,
            grandchild_3_2_1,
            grandchild_3_2_2,
        ) = self.create_service_tree()

        # Verify the structure
        self.assertEqual(len(root_1.child_ids), 0, "Root Service 1 should have no children")

        self.assertEqual(len(root_2.child_ids), 3, "Root Service 2 should have 3 children")
        self.assertEqual(root_2.child_ids[0].name, f"{self.TEST_PREFIX}Child 2.1")
        self.assertEqual(root_2.child_ids[1].name, f"{self.TEST_PREFIX}Child 2.2")
        self.assertEqual(root_2.child_ids[2].name, f"{self.TEST_PREFIX}Child 2.3")

        self.assertEqual(len(root_3.child_ids), 3, "Root Service 3 should have 3 children")
        self.assertEqual(root_3.child_ids[0].name, f"{self.TEST_PREFIX}Child 3.1")
        self.assertEqual(root_3.child_ids[1].name, f"{self.TEST_PREFIX}Child 3.2")
        self.assertEqual(root_3.child_ids[2].name, f"{self.TEST_PREFIX}Child 3.3")

        self.assertEqual(len(child_3_2.child_ids), 2, "Child 3.2 should have 2 grandchildren")
        self.assertEqual(child_3_2.child_ids[0].name, f"{self.TEST_PREFIX}Grandchild 3.2.1")
        self.assertEqual(child_3_2.child_ids[1].name, f"{self.TEST_PREFIX}Grandchild 3.2.2")

        # Verify the root_id is set correctly for all services
        all_services = (
            root_1
            + root_2
            + root_3
            + child_2_1
            + child_2_2
            + child_2_3
            + child_3_1
            + child_3_2
            + child_3_3
            + grandchild_3_2_1
            + grandchild_3_2_2
        )
        for service in all_services:
            if service in [root_1, root_2, root_3]:
                self.assertEqual(service.root_id, service, f"{service.name} should be its own root")
            elif service in [child_2_1, child_2_2, child_2_3]:
                self.assertEqual(
                    service.root_id,
                    root_2,
                    f"{service.name} should have Root Service 2 as root",
                )
            else:
                self.assertEqual(
                    service.root_id,
                    root_3,
                    f"{service.name} should have Root Service 3 as root",
                )

        # Verify deadlines for children of Root Service 2
        self.assertEqual(
            child_2_1.deadline,
            date(2024, 1, 31),
            "Child 2.1 deadline should be 1 day before Root Service 2",
        )
        self.assertEqual(
            child_2_2.deadline,
            date(2024, 1, 30),
            "Child 2.2 deadline should be 2 days before Root Service 2",
        )
        self.assertEqual(
            child_2_3.deadline,
            date(2024, 1, 29),
            "Child 2.3 deadline should be 3 days before Root Service 2",
        )

        # Verify deadlines for children of Root Service 3
        self.assertEqual(
            child_3_1.deadline,
            date(2024, 2, 29),
            "Child 3.1 deadline should be 1 day before Root Service 3",
        )
        self.assertEqual(
            child_3_2.deadline,
            date(2024, 2, 28),
            "Child 3.2 deadline should be 2 days before Root Service 3",
        )
        self.assertEqual(
            child_3_3.deadline,
            date(2024, 2, 27),
            "Child 3.3 deadline should be 3 days before Root Service 3",
        )

        # Verify deadlines for grandchildren of Child 3.2
        self.assertEqual(
            grandchild_3_2_1.deadline,
            date(2024, 3, 2),
            "Grandchild 3.2.1 deadline should be 1 day after Root Service 3",
        )
        self.assertEqual(
            grandchild_3_2_2.deadline,
            date(2024, 3, 3),
            "Grandchild 3.2.2 deadline should be 2 days after Root Service 3",
        )

    def test_service_search_and_order(self):
        self.create_service_tree()

        # Search for all services created in this test
        services = self.env["riverflow.service"].search([("name", "like", f"{self.TEST_PREFIX}%")])

        # Expected order of services: Root services by name, child services by date
        # | indented_name              | deadline   |
        # |----------------------------|------------|
        # | Root Service 1             | 2024-01-01 |
        # | Root Service 2             | 2024-02-01 |
        # |     Child 2.3              | 2024-01-29 |
        # |     Child 2.2              | 2024-01-30 |
        # |     Child 2.1              | 2024-01-31 |
        # | Root Service 3             | 2024-03-01 |
        # |     Child 3.3              | 2024-02-27 |
        # |     Child 3.2              | 2024-02-28 |
        # |         Grandchild 3.2.1   | 2024-03-02 |
        # |         Grandchild 3.2.2   | 2024-03-03 |
        # |     Child 3.1              | 2024-02-29 |

        # Expected order of services
        expected_order = [
            f"{self.TEST_PREFIX}Root Service 1",
            f"{self.TEST_PREFIX}Root Service 2",
            f"{self.TEST_PREFIX}Child 2.3",
            f"{self.TEST_PREFIX}Child 2.2",
            f"{self.TEST_PREFIX}Child 2.1",
            f"{self.TEST_PREFIX}Root Service 3",
            f"{self.TEST_PREFIX}Child 3.3",
            f"{self.TEST_PREFIX}Child 3.2",
            f"{self.TEST_PREFIX}Grandchild 3.2.1",
            f"{self.TEST_PREFIX}Grandchild 3.2.2",
            f"{self.TEST_PREFIX}Child 3.1",
        ]

        # Verify the number of services
        self.assertEqual(len(services), len(expected_order), "Incorrect number of services found")

        # self.dump_services_to_console(services)

        # Verify the order of services
        for i, service in enumerate(services):
            self.assertEqual(
                service.name,
                expected_order[i],
                f"Service at position {i} should be '{expected_order[i]}', but found '{service.name}'",
            )

        # Verify parent-child relationships
        root_2 = services.filtered(lambda s: s.name == f"{self.TEST_PREFIX}Root Service 2")
        root_3 = services.filtered(lambda s: s.name == f"{self.TEST_PREFIX}Root Service 3")
        child_3_2 = services.filtered(lambda s: s.name == f"{self.TEST_PREFIX}Child 3.2")

        self.assertEqual(len(root_2.child_ids), 3, "Root Service 2 should have 3 children")
        self.assertEqual(len(root_3.child_ids), 3, "Root Service 3 should have 3 children")
        self.assertEqual(len(child_3_2.child_ids), 2, "Child 3.2 should have 2 children")

        # Verify the order of children
        self.assertEqual(
            root_2.child_ids.mapped("name"),
            [
                f"{self.TEST_PREFIX}Child 2.1",
                f"{self.TEST_PREFIX}Child 2.2",
                f"{self.TEST_PREFIX}Child 2.3",
            ],
            "Children of Root Service 2 are not in the correct order",
        )
        self.assertEqual(
            root_3.child_ids.mapped("name"),
            [
                f"{self.TEST_PREFIX}Child 3.1",
                f"{self.TEST_PREFIX}Child 3.2",
                f"{self.TEST_PREFIX}Child 3.3",
            ],
            "Children of Root Service 3 are not in the correct order",
        )
        self.assertEqual(
            child_3_2.child_ids.mapped("name"),
            [
                f"{self.TEST_PREFIX}Grandchild 3.2.1",
                f"{self.TEST_PREFIX}Grandchild 3.2.2",
            ],
            "Children of Child 3.2 are not in the correct order",
        )

    def test_change_use_project_deadline_from(self):
        (
            root_1,
            root_2,
            root_3,
            child_2_1,
            child_2_2,
            child_2_3,
            child_3_1,
            child_3_2,
            child_3_3,
            grandchild_3_2_1,
            grandchild_3_2_2,
        ) = self.create_service_tree()

        # | indented_name              | deadline   |
        # |----------------------------|------------|
        # | Root Service 1             | 2024-01-01 |
        # | Root Service 2             | 2024-02-01 |
        # |     Child 2.3              | 2024-01-29 |
        # |     Child 2.2              | 2024-01-30 |
        # |     Child 2.1              | 2024-01-31 |
        # | Root Service 3             | 2024-03-01 |
        # |     Child 3.3              | 2024-02-27 |
        # |     Child 3.2              | 2024-02-28 |
        # |         Grandchild 3.2.1   | 2024-03-02 |
        # |         Grandchild 3.2.2   | 2024-03-03 |
        # |     Child 3.1              | 2024-02-29 |

        # with self.assertRaisesRegex(UserError, "You must set the Deadline"):
        child_3_2.write({"use_project_deadline_from": "self", "project_deadline": False})

        # NOTE: Users can't clear the deadline, as asserted above. Checks below are for the odd case where a deadline is set to 'self' and then cleared.
        self.assertEqual(child_3_2.deadline, False, "The deadline should be cleared")

        services = self.env["riverflow.service"].search([("name", "like", f"{self.TEST_PREFIX}%")])
        # self.dump_services_to_console(services)
        child_3_2 = services.filtered(lambda s: s.name == f"{self.TEST_PREFIX}Child 3.2")
        self.assertEqual(child_3_2.deadline, False, "The deadline should be cleared")
        root_3 = services.filtered(lambda s: s.name == f"{self.TEST_PREFIX}Root Service 3")

        # self.dump_services_to_console(root_3.child_ids)
        # self.dump_services_to_console(services)

        last_child_id = None
        for service in root_3.child_ids.sorted(key=lambda r: r.display_order):
            last_child_id = service.id
        self.assertEqual(
            last_child_id,
            child_3_2.id,
            "Child 3.2 should be the last child of Root Service 3",
        )

    def test_create_service_with_deadline(self):
        # days_relative_to_project should be ignored when use_project_deadline_from is 'self'
        services = self.env["riverflow.service"].create(
            {
                "name": "Service 1",
                "project_deadline": "2024-01-02",
                "days_relative_to_project": -1,
            },
        )

        self.assertRecordValues(
            services,
            [
                {
                    "name": "Service 1",
                    "use_project_deadline_from": "self",
                    "project_deadline": date(2024, 1, 2),
                    "days_relative_to_project": -1,  # not relevant for 'self'
                    "deadline": date(2024, 1, 2),
                }
            ],
        )

    def test_service_tree_identical_deadlines(self):
        """Test that services with identical deadlines are ordered by daily_prio"""
        self.cleanup_test_services()

        # Create 2 root services with same deadline but different daily_prio
        root_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX} A",
                "project_deadline": "2024-06-15",
                "daily_prio": 2,
            }
        )

        root_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX} B",
                "project_deadline": "2024-06-15",
                "daily_prio": 1,
            }
        )

        # Create 3 children for root_1 with same deadline but different priorities
        child_1_1 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child",
                "parent_id": root_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-10",
                "daily_prio": 1,
            }
        )

        child_1_2 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child",
                "parent_id": root_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-10",
                "daily_prio": 2,
            }
        )

        child_1_3 = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Child",
                "parent_id": root_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-10",
                "daily_prio": 3,
            }
        )

        # Create 3 grandchildren for each child of root_1
        # Grandchildren of Child 1.1
        self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Grandchild",
                "parent_id": child_1_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-05",
                "daily_prio": 1,
            }
        )

        self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Grandchild",
                "parent_id": child_1_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-05",
                "daily_prio": 2,
            }
        )

        self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}Grandchild",
                "parent_id": child_1_1.id,
                "use_project_deadline_from": "self",
                "project_deadline": "2024-06-05",
                "daily_prio": 3,
            }
        )

        # Search for all test services
        services = self.env["riverflow.service"].search(
            [("name", "like", f"{self.TEST_PREFIX}%")],
        )

        # Debug: print the tree structure
        print("\n=== Service Tree Structure (ordered by display_order) ===")
        self.dump_services_to_console(services)

        # Verify root services are ordered by daily_prio
        root_services = services.filtered(lambda s: not s.parent_id)
        self.assertEqual(len(root_services), 2, "Should have exactly 2 root services")

        # Root with lower priority number should come first
        self.assertEqual(root_services[0].daily_prio, 1, "First root should have priority 1")
        self.assertEqual(root_services[1].daily_prio, 2, "Second root should have priority 2")

        # Verify children of root_1 are ordered by daily_prio
        root_1_children = root_1.child_ids.sorted(key=lambda r: r.display_order)
        self.assertEqual(len(root_1_children), 3, "Root 1 should have 3 children")
        self.assertEqual(root_1_children[0].daily_prio, 1, "First child of root 1 should have priority 1")
        self.assertEqual(root_1_children[1].daily_prio, 2, "Second child of root 1 should have priority 2")
        self.assertEqual(root_1_children[2].daily_prio, 3, "Third child of root 1 should have priority 3")

        # Verify grandchildren of child_1_1 are ordered by daily_prio
        gc_1_1 = child_1_1.child_ids.sorted(key=lambda r: r.display_order)
        self.assertEqual(len(gc_1_1), 3, "Child 1.1 should have 3 grandchildren")
        self.assertEqual(gc_1_1[0].daily_prio, 1)
        self.assertEqual(gc_1_1[1].daily_prio, 2)
        self.assertEqual(gc_1_1[2].daily_prio, 3)
