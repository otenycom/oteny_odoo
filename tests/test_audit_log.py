# test_audit_log.py
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLog(TransactionCase):
    """Test the audit log functionality"""

    def setUp(self):
        super().setUp()
        # Store original tracking state from registry
        self._original_tracking_state = getattr(self.env.registry, "_mail_tracking_disabled", False)
        # Ensure tracking is enabled for initial tests
        if hasattr(self.env.registry, "_mail_tracking_disabled"):
            delattr(self.env.registry, "_mail_tracking_disabled")

    def tearDown(self):
        super().tearDown()
        # Restore original tracking state
        if self._original_tracking_state:
            self.env.registry._mail_tracking_disabled = True
        elif hasattr(self.env.registry, "_mail_tracking_disabled"):
            delattr(self.env.registry, "_mail_tracking_disabled")

    def test_create_logs_insert(self):
        """Test that creating a record logs an insert"""
        # Count existing logs
        initial_count = self.env["oteny.audit.log"].search_count([])

        # Create a test partner
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner for Audit",
                "email": "test@example.com",
            }
        )

        # Check that logs were created
        new_logs = self.env["oteny.audit.log"].search(
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
        self.assertEqual(name_log.old_value, "")

    def test_write_logs_update(self):
        """Test that updating a record logs an update"""
        # Create a test partner
        partner = self.env["res.partner"].create(
            {
                "name": "Initial Name",
                "email": "initial@example.com",
            }
        )

        # Clear any logs from creation
        self.env["oteny.audit.log"].search(
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
        update_logs = self.env["oteny.audit.log"].search(
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
            self.assertEqual(name_log.old_value, "Initial Name")
            self.assertEqual(name_log.new_value, "Updated Name")

    def test_unlink_logs_delete(self):
        """Test that deleting a record logs a delete"""
        # Create a test partner
        partner = self.env["res.partner"].create(
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
        delete_logs = self.env["oteny.audit.log"].search(
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
            self.assertEqual(name_log.old_value, partner_name)
            self.assertEqual(name_log.new_value, "")

    def test_write_logs_m2m_group_add(self):
        """Test that adding a user to a group logs an update"""
        # Create a test user
        main_company = self.env.ref("base.main_company")
        user = self.env["res.users"].create(
            {
                "name": "Group Test User",
                "login": "test_group_user@example.com",
                "company_id": main_company.id,
                "company_ids": [(6, 0, [main_company.id])],
            }
        )

        # ensure the user doesn't have the group_sanitize_override
        group_html = self.env.ref("base.group_sanitize_override")
        self.assertNotIn(group_html, user.groups_id)

        # Clear any logs from creation
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.users"),
                ("record_id", "=", user.id),
            ]
        ).unlink()

        initial_groups = user.groups_id

        # Add the user to the system group
        user.write({"groups_id": [(4, group_html.id, 0)]})
        user.flush_recordset()

        # Check that update logs were created
        update_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.users"),
                ("record_id", "=", user.id),
                ("change_type", "=", "update"),
                ("field_name", "=", "groups_id"),
            ]
        )

        self.assertEqual(len(update_logs), 1, "One update log for groups_id should be created")

        log = update_logs

        final_groups = user.groups_id
        # Compare display names directly - they contain group names like 'Technical / Access to export feature'
        expected_prev_display = ", ".join(sorted(g.display_name for g in initial_groups))
        expected_new_display = ", ".join(sorted(g.display_name for g in final_groups))

        actual_prev_display = (
            ", ".join(sorted(log.old_value_display_name.split(", "))) if log.old_value_display_name else ""
        )
        actual_new_display = (
            ", ".join(sorted(log.new_value_display_name.split(", "))) if log.new_value_display_name else ""
        )

        self.assertEqual(actual_prev_display, expected_prev_display)
        self.assertEqual(actual_new_display, expected_new_display)

    def test_no_recursion_on_audit_log(self):
        """Test that audit log operations don't trigger recursive logging"""
        # Create an audit log entry directly
        initial_count = self.env["oteny.audit.log"].search_count([])

        log = self.env["oteny.audit.log"].create(
            {
                "model_name": "test.model",
                "record_id": 1,
                "field_name": "test_field",
                "old_value": "old",
                "new_value": "new",
                "change_type": "update",
            }
        )

        # Check that no additional logs were created for the audit log itself
        new_count = self.env["oteny.audit.log"].search_count(
            [
                ("model_name", "=", "oteny.audit.log"),
            ]
        )

        self.assertEqual(new_count, 0, "No audit logs should be created for audit log model itself")

    def test_tracking_disable_system_wide(self):
        """Test that tracking can be disabled and enabled system-wide"""
        # Test that we can disable tracking
        self.env["oteny.audit.log"].disable_mail_tracking_system_wide()

        # Verify registry flag is set
        self.assertTrue(
            getattr(self.env.registry, "_mail_tracking_disabled", False),
            "Registry flag should be set when tracking is disabled",
        )

        # Test that we can enable tracking
        self.env["oteny.audit.log"].enable_mail_tracking_system_wide()

        # Verify registry flag is cleared
        self.assertFalse(
            getattr(self.env.registry, "_mail_tracking_disabled", False),
            "Registry flag should be cleared when tracking is enabled",
        )

        # Test that the configuration parameter is also set correctly
        disabled_param = self.env["ir.config_parameter"].sudo().get_param("mail.tracking_disabled")
        self.assertEqual(disabled_param, "0", "Configuration parameter should be '0' when enabled")
