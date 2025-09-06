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

        # Debug output to see what logs we have
        print(f"\nDebug test_create_then_write_ordering: Found {len(logs)} logs")
        for i, log in enumerate(logs):
            print(f"  Log {i}: field={log.field_name}, type={log.change_type}, new={log.new_value}")

        # Filter out computed_field which might be set during creation
        non_computed_logs = logs.filtered(lambda l: l.field_name != "computed_field")

        # Should have exactly 2 logs for 'name' field: 1 insert, 1 update
        self.assertEqual(
            len(non_computed_logs), 2, "Should have 2 audit logs for 'name' field (1 insert, 1 update)"
        )

        # First log should be the insert
        self.assertEqual(non_computed_logs[0].change_type, "i", "First log should be insert")
        self.assertEqual(non_computed_logs[0].field_name, "name", "First log should be for name field")
        self.assertEqual(non_computed_logs[0].new_value, "Initial Name", "Insert should have initial value")
        self.assertEqual(non_computed_logs[0].old_value, "", "Insert should have empty old value")

        # Second log should be the update
        self.assertEqual(non_computed_logs[1].change_type, "u", "Second log should be update")
        self.assertEqual(non_computed_logs[1].field_name, "name", "Second log should be for name field")
        self.assertEqual(
            non_computed_logs[1].old_value, "Initial Name", "Update should have initial as old value"
        )
        self.assertEqual(non_computed_logs[1].new_value, "Updated Name", "Update should have updated value")

        # Verify ordering in aggregated view as well
        aggregated_logs = self.aggregated_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
                ("is_child_log", "=", False),  # Only direct logs
                ("field_name", "!=", "computed_field"),  # Exclude computed field
            ],
        )

        # In DESC order, update should come first, then insert
        self.assertEqual(len(aggregated_logs), 2, "Should have 2 aggregated logs for 'name' field")
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

    def test_computed_field_during_create_ordering(self):
        """Test that computed fields during creation should log as inserts, not updates appearing before inserts.

        This test reproduces the issue where computed fields (like company_id computed from employee_id)
        trigger write operations during record creation, causing 'u' (update) logs to appear before 'i' (insert) logs.
        """
        # Create a parent record with a name that triggers the computed field
        parent = self.parent_model.create({"name": "Test Name"})

        # Flush to ensure all operations are complete
        parent.flush_recordset()

        # Get all audit logs for this parent record
        logs = self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
            ],
            order="id ASC",  # Order by ID ascending to see chronological order
        )

        print(f"\nDebug: Found {len(logs)} logs for parent record {parent.id}")
        print(f"Debug: Parent record values: name={parent.name}, computed_field={parent.computed_field}")
        for i, log in enumerate(logs):
            print(
                f"Debug: Log {i} - field: {log.field_name}, type: {log.change_type}, "
                f"old: '{log.old_value}', new: '{log.new_value}', id: {log.id}"
            )

        # Should have at least 2 logs (name insert and computed_field)
        self.assertGreaterEqual(len(logs), 2, "Should have at least 2 audit logs")

        # Find the first update and last insert
        first_update_index = -1
        last_insert_index = -1

        for i, log in enumerate(logs):
            if log.change_type == "u" and first_update_index == -1:
                first_update_index = i
            if log.change_type == "i":
                last_insert_index = i

        # Key assertion: No update should come before any insert during creation
        # This test SHOULD FAIL with current implementation where computed fields
        # trigger updates that get logged before the inserts
        if first_update_index != -1:
            self.assertGreater(
                first_update_index,
                last_insert_index,
                f"During creation, all inserts should be logged before any updates. "
                f"Found update at index {first_update_index} but last insert at index {last_insert_index}. "
                f"Log details: {[(log.field_name, log.change_type, log.id) for log in logs]}",
            )

        # Check that computed_field was set
        computed_field_logs = logs.filtered(lambda l: l.field_name == "computed_field")
        self.assertTrue(computed_field_logs, "Should have log for computed_field")

        # The computed field should ideally be logged as an insert, not an update
        # This assertion will also fail with current implementation
        self.assertEqual(
            computed_field_logs[0].change_type,
            "i",
            f"Computed field during creation should be logged as insert, not '{computed_field_logs[0].change_type}'",
        )

        # Verify the specific case: computed_field (if logged as 'u') should not have lower ID than name ('i')
        name_log = logs.filtered(lambda l: l.field_name == "name" and l.change_type == "i")
        if name_log and computed_field_logs:
            self.assertLess(
                name_log[0].id,
                computed_field_logs[0].id,
                f"Name insert (ID {name_log[0].id}) should have lower ID than computed_field "
                f"(ID {computed_field_logs[0].id}, type {computed_field_logs[0].change_type})",
            )

        # Now test that subsequent writes to the newly created record are logged as updates, not inserts
        print("\nTesting subsequent write to newly created record...")

        # Write to the record after creation is complete
        parent.write({"name": "Updated After Creation"})
        parent.flush_recordset()

        # Get all logs again
        all_logs_after_update = self.log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", parent.id),
            ],
            order="id ASC",
        )

        print(f"Debug: After update, found {len(all_logs_after_update)} total logs")
        for i, log in enumerate(all_logs_after_update):
            print(
                f"Debug: Log {i} - field: {log.field_name}, type: {log.change_type}, "
                f"old: '{log.old_value}', new: '{log.new_value}', id: {log.id}"
            )

        # Should have at least 3 logs now (original name insert, computed_field insert, and name update)
        self.assertGreaterEqual(len(all_logs_after_update), 3, "Should have at least 3 logs after update")

        # Find the update log for the name field
        name_update_logs = all_logs_after_update.filtered(
            lambda l: l.field_name == "name" and l.new_value == "Updated After Creation"
        )
        self.assertEqual(len(name_update_logs), 1, "Should have exactly one update log for name")

        # This should be logged as 'u' (update), not 'i' (insert)
        self.assertEqual(
            name_update_logs[0].change_type,
            "u",
            "Subsequent write to newly created record should be logged as update, not insert",
        )

        # The old value should be the initial value
        self.assertEqual(
            name_update_logs[0].old_value,
            "Test Name",
            "Update log should have the previous value as old_value",
        )

        # Also check that computed_field gets updated and logged as 'u' this time
        computed_update_logs = all_logs_after_update.filtered(
            lambda l: l.field_name == "computed_field" and l.new_value == "Computed: Updated After Creation"
        )
        if computed_update_logs:
            self.assertEqual(
                computed_update_logs[0].change_type,
                "u",
                "Computed field update after creation should be logged as update, not insert",
            )
            print(f"Debug: Computed field update correctly logged as 'u'")
