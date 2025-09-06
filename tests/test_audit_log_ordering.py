# test_audit_log_ordering.py
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogOrdering(TransactionCase):
    """Test that audit logs are created in the correct chronological order"""

    def setUp(self):
        super().setUp()
        self.parent_model = self.env["oteny.audit.test.parent"]
        self.child_model = self.env["oteny.audit.test.child"]
        self.log_model = self.env["oteny.audit.log"]
        self.ref_model = self.env["oteny.audit.log.ref"]
        self.aggregated_model = self.env["oteny.audit.log.aggregated"]

    def test_create_then_write_ordering(self):
        """Test that when creating a record and immediately writing to it, logs are in correct order"""
        # Create a parent record and immediately write to it (before any flush)
        parent = self.parent_model.create({"name": "Initial Name"})

        # Immediately write to the same record (before flush)
        parent.write({"name": "Updated Name"})

        # Now flush to trigger the deferred logging for the write
        parent.flush_recordset()

        # Get all audit logs for this parent record
        logs = self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
            ],
            order="id ASC",  # Order by ID ascending to see chronological order
        )

        # Should have exactly 2 logs: 1 insert, 1 update
        self.assertEqual(len(logs), 2, "Should have 2 audit logs (1 insert, 1 update)")

        # First log should be the insert
        self.assertEqual(logs[0].change_type, "i", "First log should be insert")
        self.assertEqual(logs[0].field_name, "name", "First log should be for name field")
        self.assertEqual(logs[0].new_value, "Initial Name", "Insert should have initial value")
        self.assertEqual(logs[0].old_value, "", "Insert should have empty old value")

        # Second log should be the update
        self.assertEqual(logs[1].change_type, "u", "Second log should be update")
        self.assertEqual(logs[1].field_name, "name", "Second log should be for name field")
        self.assertEqual(logs[1].old_value, "Initial Name", "Update should have initial as old value")
        self.assertEqual(logs[1].new_value, "Updated Name", "Update should have updated value")

        # Verify ordering in aggregated view as well
        aggregated_logs = self.aggregated_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
                ("is_child_log", "=", False),  # Only direct logs
            ],
        )

        # In DESC order, update should come first, then insert
        self.assertEqual(len(aggregated_logs), 2, "Should have 2 aggregated logs")
        self.assertEqual(aggregated_logs[0].change_type, "u", "Most recent should be update")
        self.assertEqual(aggregated_logs[1].change_type, "i", "Older should be insert")

    def test_child_create_update_parent_ordering(self):
        """Test ordering when child is created and updated, showing in parent's audit trail"""
        # Create parent first
        parent = self.parent_model.create({"name": "Parent Record"})

        # Clear parent's own creation logs to focus on child logs
        self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
            ]
        ).unlink()

        # Create a child and immediately update it
        child = self.child_model.create({"name": "Initial Child Name", "parent_id": parent.id})

        # Immediately update the child
        child.write({"name": "Updated Child Name"})
        child.flush_recordset()

        # Get child's direct audit logs
        child_logs = self.log_model.search(
            [
                ("model_name", "=", self.child_model._name),
                ("record_id", "=", child.id),
            ],
            order="id ASC",
        )

        # Should have 3 logs: name insert, parent_id insert, name update
        self.assertGreaterEqual(len(child_logs), 3, "Should have at least 3 child logs")

        # Find the logs for the name field
        name_logs = child_logs.filtered(lambda l: l.field_name == "name")
        self.assertEqual(len(name_logs), 2, "Should have 2 logs for name field")

        # First name log should be insert
        self.assertEqual(name_logs[0].change_type, "i", "First name log should be insert")
        self.assertEqual(name_logs[0].new_value, "Initial Child Name")

        # Second name log should be update
        self.assertEqual(name_logs[1].change_type, "u", "Second name log should be update")
        self.assertEqual(name_logs[1].old_value, "Initial Child Name")
        self.assertEqual(name_logs[1].new_value, "Updated Child Name")

        # Check parent_id insert log
        parent_id_log = child_logs.filtered(lambda l: l.field_name == "parent_id")
        self.assertEqual(len(parent_id_log), 1, "Should have 1 log for parent_id")
        self.assertEqual(parent_id_log.change_type, "i", "parent_id log should be insert")

        # Verify in parent's aggregated view
        parent_view_logs = self.aggregated_model.search(
            [
                ("model_name", "=", parent._name),
                ("record_id", "=", parent.id),
                ("is_child_log", "=", True),
            ],
        )

        # Should see child logs in reverse chronological order
        child_name_logs = parent_view_logs.filtered(lambda l: l.field_name == "name")
        self.assertEqual(len(child_name_logs), 2, "Parent should see 2 child name changes")

        # Most recent first (due to DESC order)
        self.assertEqual(child_name_logs[0].change_type, "u", "Most recent should be update")
        self.assertEqual(child_name_logs[0].new_value, "Updated Child Name")

        self.assertEqual(child_name_logs[1].change_type, "i", "Older should be insert")
        self.assertEqual(child_name_logs[1].new_value, "Initial Child Name")

    def test_multiple_writes_before_flush(self):
        """Test that multiple writes before flush result in single update log"""
        # Create a record
        parent = self.parent_model.create({"name": "Name 1"})

        # Multiple writes without flush - only the last one will be logged
        parent.write({"name": "Name 2"})
        parent.write({"name": "Name 3"})
        parent.write({"name": "Name 4"})

        # Now flush all changes
        parent.flush_recordset()

        # Get all logs
        logs = self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
                ("field_name", "=", "name"),
            ],
            order="id ASC",
        )

        # Should have 2 logs: 1 insert + 1 update (multiple writes coalesce into one)
        self.assertEqual(len(logs), 2, "Should have 2 logs (1 insert + 1 final update)")

        # Verify the sequence
        self.assertEqual(logs[0].change_type, "i", "First should be insert")
        self.assertEqual(logs[0].new_value, "Name 1")

        # Only the final write is logged (intermediate values are lost)
        self.assertEqual(logs[1].change_type, "u", "Second should be update")
        self.assertEqual(logs[1].old_value, "Name 1", "Old value should be initial")
        self.assertEqual(logs[1].new_value, "Name 4", "New value should be final")

        print(f"\nLog IDs in order: {logs.mapped('id')}")
        print(
            f"Multiple writes before flush coalesce into single update: Create (Name 1) -> Update (Name 1 -> Name 4)"
        )

    def test_writes_with_intermediate_flushes(self):
        """Test that writes with intermediate flushes create separate logs"""
        # Create a record
        parent = self.parent_model.create({"name": "Name 1"})

        # Write and flush
        parent.write({"name": "Name 2"})
        parent.flush_recordset()

        # Write and flush again
        parent.write({"name": "Name 3"})
        parent.flush_recordset()

        # Write and flush once more
        parent.write({"name": "Name 4"})
        parent.flush_recordset()

        # Get all logs
        logs = self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
                ("field_name", "=", "name"),
            ],
            order="id ASC",
        )

        # Should have 4 logs: 1 insert + 3 updates (each flush creates a log)
        self.assertEqual(len(logs), 4, "Should have 4 logs (1 insert + 3 updates)")

        # Verify the sequence
        self.assertEqual(logs[0].change_type, "i", "First should be insert")
        self.assertEqual(logs[0].new_value, "Name 1")

        self.assertEqual(logs[1].change_type, "u", "Second should be update")
        self.assertEqual(logs[1].old_value, "Name 1")
        self.assertEqual(logs[1].new_value, "Name 2")

        self.assertEqual(logs[2].change_type, "u", "Third should be update")
        self.assertEqual(logs[2].old_value, "Name 2")
        self.assertEqual(logs[2].new_value, "Name 3")

        self.assertEqual(logs[3].change_type, "u", "Fourth should be update")
        self.assertEqual(logs[3].old_value, "Name 3")
        self.assertEqual(logs[3].new_value, "Name 4")

        # Verify ordering: IDs should be in ascending order
        log_ids = logs.mapped("id")
        self.assertEqual(log_ids, sorted(log_ids), "Log IDs should be in ascending order")

        print(f"\nLog IDs in order: {log_ids}")
        print(f"Each flush creates a separate log: Create -> Update1 -> Update2 -> Update3")
