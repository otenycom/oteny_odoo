from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditParentRef(TransactionCase):
    def setUp(self):
        super().setUp()
        self.parent_model = self.env["oteny.audit.test.parent"]
        self.child_model = self.env["oteny.audit.test.child"]
        self.log_model = self.env["oteny.audit.log"]
        self.parent_ref_model = self.env["oteny.audit.log.parent.ref"]
        self.aggregated_log_model = self.env["oteny.audit.log.aggregated"]

        self.parent_record = self.parent_model.create({"name": "Test Parent"})

    def dump_aggregated_log(self, parent_record):
        """Helper to print the content of the aggregated log for a given parent."""
        print(
            f"\n--- Dumping aggregated logs for {parent_record.display_name} ({parent_record._name}:{parent_record.id}) ---"
        )
        # We need to invalidate the cache for the view model to make sure we get fresh results
        self.aggregated_log_model.invalidate_model()
        aggregated_logs = self.aggregated_log_model.search(
            [
                ("model_name", "=", parent_record._name),
                ("record_id", "=", parent_record.id),
            ]
        )
        if not aggregated_logs:
            print("No aggregated logs found.")
        for log in aggregated_logs:
            print(f"  Log ID: {log.id}, Change: {log.change_type}, Is Child: {log.is_child_log}")
            if log.is_child_log:
                print(f"    Child Record: {log.child_model_name}:{log.child_record_id}")
            print(f"    Field: {log.field_display_name} ('{log.field_name}')")
            print(f"    Old Value: {log.old_value_display_name}")
            print(f"    New Value: {log.new_value_display_name}")
        print("----------------------------------------------------\n")

    def test_parent_child_ref(self):
        """Test that changes to a child record create parent references in the audit log."""
        # 1. Create a child record
        child_record = self.child_model.create({"name": "Test Child 1", "parent_id": self.parent_record.id})

        # 2. Check if a log and a parent reference were created
        log_entry = self.log_model.search(
            [
                ("model_name", "=", self.child_model._name),
                ("record_id", "=", child_record.id),
                ("change_type", "=", "i"),
                ("field_name", "=", "name"),
            ]
        )
        self.assertEqual(len(log_entry), 1, "Should find one insert log for the child.")

        parent_ref = self.parent_ref_model.search([("audit_log_id", "=", log_entry.id)])
        self.assertEqual(len(parent_ref), 1, "Should find one parent reference for the log.")
        self.assertEqual(parent_ref.parent_model_name, self.parent_model._name)
        self.assertEqual(parent_ref.parent_record_id, self.parent_record.id)

        # 3. Update the child record
        child_record.write({"name": "Test Child 1 Updated"})
        child_record.flush_recordset()

        # 4. Check if a new log and parent ref were created for the update
        update_log_entry = self.log_model.search(
            [
                ("model_name", "=", self.child_model._name),
                ("record_id", "=", child_record.id),
                ("change_type", "=", "u"),
                ("field_name", "=", "name"),
            ]
        )
        self.assertEqual(len(update_log_entry), 1, "Should find one update log for the child.")

        update_parent_ref = self.parent_ref_model.search([("audit_log_id", "=", update_log_entry.id)])
        self.assertEqual(len(update_parent_ref), 1, "Should find parent ref for the update log.")

        aggregated_logs = self.aggregated_log_model.search(
            [
                ("model_name", "=", self.parent_model._name),
                ("record_id", "=", self.parent_record.id),
            ]
        )

        self.dump_aggregated_log(self.parent_record)

        # We expect to find 3 logs for the parent, as the parent_id set is also logged:
        # - insert 'name' on child
        # - insert 'parent_id' on child
        # - update 'name' on child
        child_logs_in_aggregated = aggregated_logs.filtered(lambda r: r.is_child_log)
        self.assertEqual(len(child_logs_in_aggregated), 3, "Aggregated log should show 3 child logs.")

        # Check the insert logs (name and parent_id)
        insert_logs = child_logs_in_aggregated.filtered(lambda r: r.change_type == "i")
        self.assertEqual(len(insert_logs), 2, "Should have two insert logs for the child.")

        insert_log_name = insert_logs.filtered(lambda r: r.field_name == "name")
        self.assertEqual(len(insert_log_name), 1, "Should have one insert log for name.")
        self.assertEqual(insert_log_name.new_value, "Test Child 1")
        self.assertEqual(insert_log_name.child_model_name, self.child_model._name)
        self.assertEqual(insert_log_name.child_record_id, child_record.id)

        insert_log_parent = insert_logs.filtered(lambda r: r.field_name == "parent_id")
        self.assertEqual(len(insert_log_parent), 1, "Should have one insert log for parent_id.")
        self.assertEqual(insert_log_parent.new_value_display_name, self.parent_record.display_name)

        # Check the update log (name)
        update_logs = child_logs_in_aggregated.filtered(lambda r: r.change_type == "u")
        self.assertEqual(len(update_logs), 1, "Should have one update log for the child.")
        self.assertEqual(update_logs.field_name, "name")
        self.assertEqual(update_logs.old_value, "Test Child 1")
        self.assertEqual(update_logs.new_value, "Test Child 1 Updated")
