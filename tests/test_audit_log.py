# test_audit_log.py
from odoo.tests import TransactionCase


class TestAuditLog(TransactionCase):
    """Test the audit log functionality"""

    def setUp(self):
        super().setUp()
        self.audit_log_model = self.env["oteny.audit.log"]
        # Using res.partner as a test model since it's always available
        self.test_model = self.env["res.partner"]

    def test_create_logs_insert(self):
        """Test that creating a record logs an insert"""
        # Count existing logs
        initial_count = self.audit_log_model.search_count([])

        # Create a test partner
        partner = self.test_model.create(
            {
                "name": "Test Partner for Audit",
                "email": "test@example.com",
            }
        )

        # Check that logs were created
        new_logs = self.audit_log_model.search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
                ("change_type", "=", "insert"),
            ]
        )

        self.assertTrue(new_logs, "Insert logs should be created")

        # Check that name field was logged
        name_log = new_logs.filtered(lambda l: l.field_name == "name")
        self.assertTrue(name_log, "Name field should be logged")
        self.assertEqual(name_log.new_value, "Test Partner for Audit")
        self.assertEqual(name_log.prev_value, "")

    def test_write_logs_update(self):
        """Test that updating a record logs an update"""
        # Create a test partner
        partner = self.test_model.create(
            {
                "name": "Initial Name",
                "email": "initial@example.com",
            }
        )

        # Clear any logs from creation
        self.audit_log_model.search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        ).unlink()

        # Update the partner
        partner.write(
            {
                "name": "Updated Name",
                "email": "updated@example.com",
            }
        )

        # Force flush to trigger audit logging
        partner.flush_recordset()

        # Check that update logs were created
        update_logs = self.audit_log_model.search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
                ("change_type", "=", "update"),
            ]
        )

        self.assertTrue(update_logs, "Update logs should be created")

        # Check that name field was logged correctly
        name_log = update_logs.filtered(lambda l: l.field_name == "name")
        if name_log:
            self.assertEqual(name_log.prev_value, "Initial Name")
            self.assertEqual(name_log.new_value, "Updated Name")

    def test_unlink_logs_delete(self):
        """Test that deleting a record logs a delete"""
        # Create a test partner
        partner = self.test_model.create(
            {
                "name": "To Be Deleted",
                "email": "delete@example.com",
            }
        )

        partner_id = partner.id
        partner_name = partner.name

        # Delete the partner
        partner.unlink()

        # Check that delete logs were created
        delete_logs = self.audit_log_model.search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner_id),
                ("change_type", "=", "delete"),
            ]
        )

        self.assertTrue(delete_logs, "Delete logs should be created")

        # Check that name field was logged
        name_log = delete_logs.filtered(lambda l: l.field_name == "name")
        if name_log:
            self.assertEqual(name_log.prev_value, partner_name)
            self.assertEqual(name_log.new_value, "")

    def test_no_recursion_on_audit_log(self):
        """Test that audit log operations don't trigger recursive logging"""
        # Create an audit log entry directly
        initial_count = self.audit_log_model.search_count([])

        log = self.audit_log_model.create(
            {
                "model_name": "test.model",
                "record_id": 1,
                "field_name": "test_field",
                "prev_value": "old",
                "new_value": "new",
                "change_type": "update",
            }
        )

        # Check that no additional logs were created for the audit log itself
        new_count = self.audit_log_model.search_count(
            [
                ("model_name", "=", "oteny.audit.log"),
            ]
        )

        self.assertEqual(new_count, 0, "No audit logs should be created for audit log model itself")
