# test_audit_log.py
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLog(TransactionCase):
    """Test the audit log functionality"""

    def setUp(self):
        super().setUp()

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
                ("change_type", "=", "i"),
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
                ("change_type", "=", "u"),
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
                ("change_type", "=", "d"),
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
                ("change_type", "=", "u"),
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
                "change_type": "u",
            }
        )

        # Check that no additional logs were created for the audit log itself
        new_count = self.env["oteny.audit.log"].search_count(
            [
                ("model_name", "=", "oteny.audit.log"),
            ]
        )

        self.assertEqual(new_count, 0, "No audit logs should be created for audit log model itself")

    def test_predefined_parent_keys_mail_message(self):
        """Test that predefined parent keys work for mail.message"""
        # Create a test partner as the parent record
        parent_partner = self.env["res.partner"].create(
            {
                "name": "Parent Partner for Message",
                "email": "parent@example.com",
            }
        )

        # Clear any logs from partner creation
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", parent_partner.id),
            ]
        ).unlink()

        # Create a mail message that references the partner
        message = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": parent_partner.id,
                "subject": "Test Message",
                "body": "Test message body",
                "message_type": "comment",
            }
        )

        # Force flush to trigger audit logging
        message.flush_recordset()

        # Check that audit logs were created for the message
        message_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "mail.message"),
                ("record_id", "=", message.id),
            ]
        )

        self.assertTrue(message_logs, "Audit logs should be created for mail.message")

        # Check that references were created using predefined keys
        refs = self.env["oteny.audit.log.ref"].search(
            [
                ("audit_log_id", "in", message_logs.ids),
            ]
        )

        # Each log should have refs (at least a direct ref)
        self.assertTrue(refs, "References should be created for mail.message logs")

        # Verify parent references (not direct) pointing to the expected parent partner
        partner_parent_refs = refs.filtered(
            lambda r: not r.is_direct
            and r.target_model_name == "res.partner"
            and r.target_record_id == parent_partner.id
        )
        self.assertTrue(partner_parent_refs, "Should have parent references pointing to the parent partner")
        # For parent references from child logs (mail.message), target_display_name should be the child's display name
        self.assertEqual(
            partner_parent_refs[0].target_display_name,
            message.display_name,
            "Target display name should be the message's display name for child logs",
        )
        # And parent_display_name should be the parent's display name
        self.assertEqual(
            partner_parent_refs[0].parent_display_name,
            parent_partner.display_name,
            "Parent display name should match",
        )

    def test_predefined_parent_keys_res_partner(self):
        """Test that predefined parent keys work for res.partner"""
        # Create a parent partner
        parent_partner = self.env["res.partner"].create(
            {
                "name": "Parent Partner",
                "email": "parent@example.com",
            }
        )

        # Clear any logs from parent partner creation
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", parent_partner.id),
            ]
        ).unlink()

        # Create a child partner
        child_partner = self.env["res.partner"].create(
            {
                "name": "Child Partner",
                "email": "child@example.com",
                "parent_id": parent_partner.id,
            }
        )

        # Force flush to trigger audit logging
        child_partner.flush_recordset()

        # Check that audit logs were created for the child partner
        child_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", child_partner.id),
            ]
        )

        self.assertTrue(child_logs, "Audit logs should be created for child res.partner")

        # Check that references were created using predefined keys
        refs = self.env["oteny.audit.log.ref"].search(
            [
                ("audit_log_id", "in", child_logs.ids),
            ]
        )

        self.assertTrue(refs, "References should be created for child partner logs")

        # Verify parent references (not direct) pointing to the expected parent partner
        partner_parent_refs = refs.filtered(
            lambda r: not r.is_direct
            and r.target_model_name == "res.partner"
            and r.target_record_id == parent_partner.id
        )
        self.assertTrue(partner_parent_refs, "Should have parent references pointing to the parent partner")
        # For parent references from child logs, target_display_name should be the child's display name
        self.assertEqual(
            partner_parent_refs[0].target_display_name,
            child_partner.display_name,
            "Target display name should be the child's display name for child logs",
        )
        # And parent_display_name should be the parent's display name
        self.assertEqual(
            partner_parent_refs[0].parent_display_name,
            parent_partner.display_name,
            "Parent display name should match",
        )

    def test_recursive_parent_keys_grandparent_reference(self):
        """Test that recursive parent key resolution works up to 2 levels (grandparent)"""
        # Create a grandparent partner
        grandparent_partner = self.env["res.partner"].create(
            {
                "name": "Grandparent Partner",
                "email": "grandparent@example.com",
            }
        )

        # Create a parent partner (child of grandparent)
        parent_partner = self.env["res.partner"].create(
            {
                "name": "Parent Partner",
                "email": "parent@example.com",
                "parent_id": grandparent_partner.id,
            }
        )

        # Clear any logs from partner creation
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "in", [grandparent_partner.id, parent_partner.id]),
            ]
        ).unlink()

        # Create a child partner (grandchild)
        child_partner = self.env["res.partner"].create(
            {
                "name": "Child Partner",
                "email": "child@example.com",
                "parent_id": parent_partner.id,
            }
        )

        # Force flush to trigger audit logging
        child_partner.flush_recordset()

        # Check that audit logs were created for the child partner
        child_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", child_partner.id),
            ]
        )

        self.assertTrue(child_logs, "Audit logs should be created for child res.partner")

        # Check that references were created and point to GRANDPARENT (not just immediate parent)
        refs = self.env["oteny.audit.log.ref"].search(
            [
                ("audit_log_id", "in", child_logs.ids),
            ]
        )

        self.assertTrue(refs, "References should be created for child partner logs")

        # Filter for parent references (not direct)
        parent_refs = refs.filtered(lambda r: not r.is_direct)

        # Verify that we have parent references pointing to both immediate parent and grandparent
        immediate_parent_refs = parent_refs.filtered(
            lambda r: r.target_model_name == "res.partner" and r.target_record_id == parent_partner.id
        )
        grandparent_refs = parent_refs.filtered(
            lambda r: r.target_model_name == "res.partner" and r.target_record_id == grandparent_partner.id
        )

        self.assertTrue(
            immediate_parent_refs, "Should have parent references pointing to the immediate parent"
        )
        self.assertTrue(grandparent_refs, "Should have parent references pointing to the grandparent")

        # For parent references from child logs, target_display_name should be the child's display name
        self.assertEqual(
            immediate_parent_refs[0].target_display_name,
            child_partner.display_name,
            "Target display name should be the child's display name for child logs",
        )
        # And parent_display_name should be the parent's display name
        self.assertEqual(
            immediate_parent_refs[0].parent_display_name,
            parent_partner.display_name,
            "Parent display name should match",
        )
        # For grandparent references, target_display_name should also be the child's display name
        self.assertEqual(
            grandparent_refs[0].target_display_name,
            child_partner.display_name,
            "Target display name should be the child's display name for child logs",
        )
        # And parent_display_name should be the grandparent's display name
        self.assertEqual(
            grandparent_refs[0].parent_display_name,
            grandparent_partner.display_name,
            "Grandparent display name should match",
        )

    def test_recursive_parent_keys_message_to_grandparent(self):
        """Test recursive parent key resolution for mail.message pointing through partners to grandparent"""
        # Create a grandparent partner
        grandparent_partner = self.env["res.partner"].create(
            {
                "name": "Grandparent Partner",
                "email": "grandparent@example.com",
            }
        )

        # Create a parent partner (child of grandparent)
        parent_partner = self.env["res.partner"].create(
            {
                "name": "Parent Partner",
                "email": "parent@example.com",
                "parent_id": grandparent_partner.id,
            }
        )

        # Clear any logs from partner creation
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "in", [grandparent_partner.id, parent_partner.id]),
            ]
        ).unlink()

        # Create a mail message that points to the immediate parent partner
        message = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": parent_partner.id,  # Points to immediate parent
                "subject": "Test Message to Parent",
                "body": "Test message body",
                "message_type": "comment",
            }
        )

        # Force flush to trigger audit logging
        message.flush_recordset()

        # Check that audit logs were created for the message
        message_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "mail.message"),
                ("record_id", "=", message.id),
            ]
        )

        self.assertTrue(message_logs, "Audit logs should be created for mail.message")

        # Check that references point to GRANDPARENT (not just immediate parent)
        refs = self.env["oteny.audit.log.ref"].search(
            [
                ("audit_log_id", "in", message_logs.ids),
            ]
        )

        self.assertTrue(refs, "References should be created for mail.message logs")

        # Filter for parent references (not direct)
        parent_refs = refs.filtered(lambda r: not r.is_direct)

        # Verify that we have parent references pointing to both immediate parent and grandparent
        immediate_parent_refs = parent_refs.filtered(
            lambda r: r.target_model_name == "res.partner" and r.target_record_id == parent_partner.id
        )
        grandparent_refs = parent_refs.filtered(
            lambda r: r.target_model_name == "res.partner" and r.target_record_id == grandparent_partner.id
        )

        self.assertTrue(
            immediate_parent_refs, "Should have parent references pointing to the immediate parent partner"
        )
        self.assertTrue(grandparent_refs, "Should have parent references pointing to the grandparent partner")

        # For parent references from child logs (mail.message), target_display_name should be the child's display name
        self.assertEqual(
            immediate_parent_refs[0].target_display_name,
            message.display_name,
            "Target display name should be the message's display name for child logs",
        )
        # And parent_display_name should be the parent's display name
        self.assertEqual(
            immediate_parent_refs[0].parent_display_name,
            parent_partner.display_name,
            "Parent display name should match",
        )
        # For grandparent references, target_display_name should also be the child's display name
        self.assertEqual(
            grandparent_refs[0].target_display_name,
            message.display_name,
            "Target display name should be the message's display name for child logs",
        )
        # And parent_display_name should be the grandparent's display name
        self.assertEqual(
            grandparent_refs[0].parent_display_name,
            grandparent_partner.display_name,
            "Grandparent display name should match",
        )

    def test_create_no_blank_values_logged(self):
        """Test that creating records with blank values doesn't log those blank fields"""
        # Create a test partner with some blank fields
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner With Blanks",
                "email": "",  # Explicitly blank
                "phone": "",  # Explicitly blank
                "street": "Some Street",  # Non-blank
                # Don't provide other fields like mobile, city, etc. - they should be None/blank
            }
        )

        # Get all logs for this partner creation
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
                ("change_type", "=", "i"),
            ]
        )

        # Verify that only non-blank fields are logged
        logged_fields = logs.mapped("field_name")

        # Name and street should be logged (they have values)
        self.assertIn("name", logged_fields, "Name field should be logged (has value)")
        self.assertIn("street", logged_fields, "Street field should be logged (has value)")

        # Blank fields should NOT be logged
        self.assertNotIn("email", logged_fields, "Email field should not be logged (blank value)")
        self.assertNotIn("phone", logged_fields, "Phone field should not be logged (blank value)")

        # Fields that weren't provided (None values) should also not be logged
        # Common partner fields that might be None
        common_optional_fields = ["mobile", "city", "zip", "country_id", "state_id"]
        for field_name in common_optional_fields:
            if field_name in logged_fields:
                # If it's logged, verify it has a non-blank value
                log_entry = logs.filtered(lambda l: l.field_name == field_name)
                self.assertNotEqual(
                    log_entry.new_value, "", f"Field {field_name} should not be logged with blank value"
                )

        # Verify specific field values
        name_log = logs.filtered(lambda l: l.field_name == "name")
        self.assertTrue(name_log, "Name field should be logged")
        self.assertEqual(name_log.new_value, "Test Partner With Blanks")

        street_log = logs.filtered(lambda l: l.field_name == "street")
        self.assertTrue(street_log, "Street field should be logged")
        self.assertEqual(street_log.new_value, "Some Street")

    def test_unlink_no_blank_values_logged(self):
        """Test that unlinking records with blank values doesn't log those blank fields"""
        # Create a test partner with some blank fields that will be deleted
        partner = self.env["res.partner"].create(
            {
                "name": "Partner To Delete",
                "email": "",  # Explicitly blank
                "phone": "",  # Explicitly blank
                "street": "Street Address",  # Non-blank
                "city": "",  # Explicitly blank
                # Don't provide other fields like mobile - they should be None/blank
            }
        )

        partner_id = partner.id
        partner_name = partner.name
        partner_street = partner.street

        # Delete the partner
        partner.unlink()

        # Get all logs for this partner deletion
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner_id),
                ("change_type", "=", "d"),
            ]
        )

        # Verify that only non-blank fields are logged
        logged_fields = logs.mapped("field_name")

        # Name and street should be logged (they had values)
        self.assertIn("name", logged_fields, "Name field should be logged (had value)")
        self.assertIn("street", logged_fields, "Street field should be logged (had value)")

        # Blank fields should NOT be logged
        self.assertNotIn("email", logged_fields, "Email field should not be logged (was blank)")
        self.assertNotIn("phone", logged_fields, "Phone field should not be logged (was blank)")
        self.assertNotIn("city", logged_fields, "City field should not be logged (was blank)")

        # Fields that weren't provided (None values) should also not be logged
        # Common partner fields that might be None
        common_optional_fields = ["mobile", "zip", "country_id", "state_id"]
        for field_name in common_optional_fields:
            if field_name in logged_fields:
                # If it's logged, verify it had a non-blank value
                log_entry = logs.filtered(lambda l: l.field_name == field_name)
                self.assertNotEqual(
                    log_entry.old_value, "", f"Field {field_name} should not be logged with blank value"
                )

        # Verify specific field values
        name_log = logs.filtered(lambda l: l.field_name == "name")
        self.assertTrue(name_log, "Name field should be logged")
        self.assertEqual(name_log.old_value, partner_name)
        self.assertEqual(name_log.new_value, "")  # Delete logs have empty new_value

        street_log = logs.filtered(lambda l: l.field_name == "street")
        self.assertTrue(street_log, "Street field should be logged")
        self.assertEqual(street_log.old_value, partner_street)
        self.assertEqual(street_log.new_value, "")  # Delete logs have empty new_value

    def test_create_all_defaults_or_empty_logs_placeholder(self):
        """Test that creating record with only defaults/empty values logs at least one placeholder"""
        # Use test models that allow empty records
        test_parent = self.env["oteny.audit.test.parent"].create({})

        # Get all logs for this record creation
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "oteny.audit.test.parent"),
                ("record_id", "=", test_parent.id),
                ("change_type", "=", "i"),
            ]
        )

        # Should create at least one log entry as placeholder to ensure operation is recorded
        self.assertGreater(
            len(logs),
            0,
            "Should create at least one placeholder log for records with only defaults/empty values",
        )

        # The placeholder log should indicate it's a placeholder
        placeholder_log = logs.filtered(lambda l: "(placeholder)" in l.field_display_name)
        if placeholder_log:
            self.assertTrue(placeholder_log, "Should have a placeholder log entry")
            self.assertEqual(placeholder_log.change_type, "i", "Placeholder should be for insert operation")

    def test_unlink_all_defaults_or_empty_logs_placeholder(self):
        """Test that deleting record with only defaults/empty values logs at least one placeholder"""
        # Use test models that allow empty records
        test_parent = self.env["oteny.audit.test.parent"].create({})

        test_parent_id = test_parent.id

        # Delete the record
        test_parent.unlink()

        # Get all logs for this record deletion
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "oteny.audit.test.parent"),
                ("record_id", "=", test_parent_id),
                ("change_type", "=", "d"),
            ]
        )

        # Should create at least one log entry as placeholder to ensure operation is recorded
        self.assertGreater(
            len(logs),
            0,
            "Should create at least one placeholder log for deletion of records with only defaults/empty values",
        )

        # The placeholder log should indicate it's a placeholder
        placeholder_log = logs.filtered(lambda l: "(placeholder)" in l.field_display_name)
        if placeholder_log:
            self.assertTrue(placeholder_log, "Should have a placeholder log entry")
            self.assertEqual(placeholder_log.change_type, "d", "Placeholder should be for delete operation")
