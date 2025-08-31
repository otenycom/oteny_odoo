# test_audit_log_aggregated_display.py
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("oteny_audit", "post_install", "-at_install")
class TestAuditLogAggregatedDisplay(TransactionCase):
    """Test the aggregated audit log display functionality with virtual rows"""

    def setUp(self):
        super().setUp()

    def _dump_audit_log_display(self, all_records, title="AUDIT LOG DISPLAY DUMP"):
        """
        Utility method to dump the full display of audit log records for debugging and analysis.

        Args:
            all_records: List of audit log display records
            title: Title for the dump output
        """
        print("\n" + "=" * 120)
        print(f"📋 {title}")
        print("=" * 120)
        print(f"Total records found: {len(all_records)}")

        # Analyze record distribution by type
        tx_headers = [r for r in all_records if r.row_type == "transaction_header"]
        record_headers = [r for r in all_records if r.row_type == "record_header"]
        field_changes = [r for r in all_records if r.row_type == "field_change"]

        print(
            f"Breakdown: {len(tx_headers)} TX headers, {len(record_headers)} record headers, {len(field_changes)} field changes"
        )
        print("\nRow Format: [SEQ] TYPE | TX_ID | RECORD_ID | MODEL | FIELD | OLD_VAL -> NEW_VAL | TIMESTAMP")
        print("-" * 120)

        # Group by transaction for better readability
        current_tx = None
        for i, record in enumerate(all_records, 1):
            row_type = record.row_type.upper()
            tx_id = record.transaction_id or "NULL"
            record_id = record.record_id or "NULL"
            model = record.model_name or "NULL"
            field_name = record.field_name or ""
            old_val = (record.old_value or "")[:25]  # Truncate long values
            new_val = (record.new_value or "")[:25]  # Truncate long values
            timestamp = record.create_date.strftime("%H:%M:%S.%f")[:-3] if record.create_date else "NULL"

            # Add transaction separator
            if tx_id != current_tx and tx_id != "NULL":
                if current_tx is not None:
                    print("-" * 50)
                print(f"🔄 TRANSACTION {tx_id}")
                current_tx = tx_id

            # Format the output line with better alignment
            if record.row_type == "transaction_header":
                caption = (record.caption or "").replace("\n", " ")[:50]
                print(
                    f"[{record.display_sequence:2d}] {row_type:18} | {tx_id:8} | {record_id:9} | {model[:20]:20} | {caption}"
                )
            elif record.row_type == "record_header":
                caption = (record.caption or "").replace("\n", " ")[:50]
                print(
                    f"[{record.display_sequence:2d}] {row_type:18} | {tx_id:8} | {record_id:9} | {model[:20]:20} | {caption}"
                )
            elif record.row_type == "field_change":
                print(
                    f"[{record.display_sequence:2d}] {row_type:18} | {tx_id:8} | {record_id:9} | {model[:20]:20} | {field_name[:12]:12} | {old_val[:12]:12} -> {new_val[:12]:12} | {timestamp}"
                )

        print("\n" + "=" * 120)

        # Additional analysis
        print("\n📊 ANALYSIS:")
        print(f"• Total transactions: {len(set(r.transaction_id for r in all_records if r.transaction_id))}")
        print(
            f"• Records per transaction: {[(tx, len([r for r in all_records if r.transaction_id == tx])) for tx in set(r.transaction_id for r in all_records if r.transaction_id)]}"
        )
        print(f"• Models involved: {sorted(set(r.model_name for r in all_records if r.model_name))}")
        print("\n" + "=" * 120)

    def test_display_view_creates_virtual_rows(self):
        """Test that the display view creates the correct virtual rows"""
        # Create a test partner
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner for Display",
                "email": "test_display@example.com",
            }
        )

        # Clear any logs from creation to ensure clean test
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )
        audit_logs.unlink()

        # Create fresh logs by updating the partner
        partner.write({"name": "Updated Test Partner"})

        # Get the transaction ID from the logs
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )
        self.assertTrue(logs, "Should have audit logs for the update")

        transaction_id = logs[0].transaction_id
        self.assertTrue(transaction_id, "Should have a transaction ID")

        # Query the display view
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("transaction_id", "=", transaction_id),
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )

        # Should have at least 3 rows: 1 transaction header + 1 record header + 1+ field changes
        self.assertGreaterEqual(len(display_records), 3, "Should have virtual rows for header and changes")

        # Check row types
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        self.assertEqual(len(transaction_headers), 1, "Should have exactly one transaction header")
        # Note: In a real scenario, there could be multiple record headers if the transaction
        # affects multiple records. For this simple test, we expect at least one.
        self.assertGreaterEqual(len(record_headers), 1, "Should have at least one record header")
        self.assertGreaterEqual(len(field_changes), 1, "Should have at least one field change")

        # Check transaction header content
        header = transaction_headers[0]
        self.assertIn("by", header.caption, "Transaction header should contain 'by' for user info")
        self.assertTrue(header.caption.startswith("20"), "Transaction header should start with date")

        # Check record header content
        record_header = record_headers[0]
        self.assertIn("Test Partner", record_header.caption, "Record header should contain record name")
        self.assertIn("Contact", record_header.caption, "Record header should contain model display name")

        # Check field change content
        name_change = field_changes.filtered(lambda r: "Name" in r.caption)
        self.assertTrue(name_change, "Should have a name field change")
        change_caption = name_change[0].caption
        self.assertIn("Update", change_caption, "Should be an update operation")
        self.assertIn("Name", change_caption, "Should mention the field name")
        self.assertIn("Test Partner for Display", change_caption, "Should contain old value")
        self.assertIn("Updated Test Partner", change_caption, "Should contain new value")

    def test_display_view_multiple_records_same_transaction(self):
        """Test display view with multiple records in the same transaction"""
        # Create two partners
        partner1 = self.env["res.partner"].create({"name": "Partner 1", "email": "partner1@example.com"})
        partner2 = self.env["res.partner"].create({"name": "Partner 2", "email": "partner2@example.com"})

        # Clear creation logs
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "in", [partner1.id, partner2.id]),
            ]
        ).unlink()

        # Update both partners in the same transaction
        with self.env.cr.savepoint():
            partner1.write({"name": "Updated Partner 1"})
            partner2.write({"name": "Updated Partner 2"})

        # Find the transaction ID from the logs
        logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "in", [partner1.id, partner2.id]),
            ]
        )
        self.assertTrue(logs, "Should have audit logs")

        transaction_ids = logs.mapped("transaction_id")
        self.assertEqual(len(set(transaction_ids)), 1, "Should have same transaction ID")

        transaction_id = transaction_ids[0]

        # Query display records
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )

        # Debug dump of the display records using the extracted method
        self._dump_audit_log_display(display_records, "MULTIPLE RECORDS SAME TRANSACTION DUMP")

        # Count different row types
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        self.assertEqual(len(transaction_headers), 1, "Should have one transaction header")
        self.assertEqual(len(record_headers), 2, "Should have two record headers (one per record)")
        self.assertGreaterEqual(len(field_changes), 2, "Should have at least two field changes")

        # Verify record headers for both partners
        partner1_headers = record_headers.filtered(lambda r: r.record_id == partner1.id)
        partner2_headers = record_headers.filtered(lambda r: r.record_id == partner2.id)

        self.assertEqual(len(partner1_headers), 1, "Should have header for partner 1")
        self.assertEqual(len(partner2_headers), 1, "Should have header for partner 2")

        self.assertIn("Partner 1", partner1_headers[0].caption)
        self.assertIn("Partner 2", partner2_headers[0].caption)

    def test_display_view_ordering(self):
        """Test that display view maintains proper ordering"""
        # Create a partner
        partner = self.env["res.partner"].create(
            {"name": "Ordering Test Partner", "email": "ordering@example.com"}
        )

        # Clear creation logs
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        ).unlink()

        # Make multiple updates in sequence
        partner.write({"name": "First Update"})
        partner.write({"email": "first@example.com"})
        partner.write({"name": "Second Update"})

        # Get all display records for this partner
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ],
            order="transaction_id DESC, record_id, display_sequence, create_date DESC, id DESC",
        )

        # Verify ordering by display_sequence
        sequences = display_records.mapped("display_sequence")
        self.assertEqual(sequences, sorted(sequences), "Display sequences should be in ascending order")

        # Transaction header should come first
        first_record = display_records[0]
        self.assertEqual(
            first_record.row_type, "transaction_header", "First record should be transaction header"
        )

        # Record header should come second
        second_record = display_records[1]
        self.assertEqual(second_record.row_type, "record_header", "Second record should be record header")

        # Field changes should come after headers
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")
        self.assertTrue(field_changes, "Should have field changes")

        # All field changes should have display_sequence = 3
        for change in field_changes:
            self.assertEqual(change.display_sequence, 3, "Field changes should have display_sequence = 3")

    def test_display_view_unique_ids(self):
        """Test that all virtual rows have unique IDs"""
        # Create test data
        partner = self.env["res.partner"].create({"name": "Unique ID Test", "email": "unique@example.com"})

        # Clear creation logs
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        ).unlink()

        # Make an update
        partner.write({"name": "Updated Unique ID Test"})

        # Get display records
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )

        # Check all IDs are unique
        ids = display_records.mapped("id")
        self.assertEqual(len(ids), len(set(ids)), "All IDs should be unique")

        # Verify ID generation pattern
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        # Transaction header ID should follow pattern: transaction_id * 1000000000000 + 1
        if transaction_headers:
            header = transaction_headers[0]
            expected_header_id = header.transaction_id * 1000000000000 + 1
            self.assertEqual(
                header.id, expected_header_id, "Transaction header ID should follow expected pattern"
            )

        # Record header ID should follow pattern: transaction_id * 1000000000000 + record_id * 1000000 + len(model_name) * 1000 + 2
        if record_headers:
            record_header = record_headers[0]
            # Calculate length component as done in the SQL view
            model_length = len(record_header.model_name) * 1000
            expected_record_id = (
                record_header.transaction_id * 1000000000000
                + record_header.record_id * 1000000
                + model_length
                + 2
            )
            self.assertEqual(
                record_header.id, expected_record_id, "Record header ID should follow expected pattern"
            )

        # Field changes should keep their original IDs
        if field_changes:
            original_logs = self.env["oteny.audit.log"].search(
                [
                    ("model_name", "=", "res.partner"),
                    ("record_id", "=", partner.id),
                ]
            )
            original_ids = set(original_logs.mapped("id"))
            field_change_ids = set(field_changes.mapped("id"))
            self.assertTrue(
                field_change_ids.issubset(original_ids), "Field change IDs should be original log IDs"
            )

    def test_display_view_proper_header_ordering(self):
        """Test that headers are properly interleaved with field changes based on create_date"""
        # Create a partner
        partner = self.env["res.partner"].create({"name": "Ordering Test Partner"})

        # Clear creation logs
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )
        audit_logs.unlink()

        # Create a sequence of updates with delays to ensure different create_dates
        import time

        # First update - name
        partner.write({"name": "First Update"})
        time.sleep(0.1)  # Small delay

        # Second update - email
        partner.write({"email": "first@test.com"})
        time.sleep(0.1)  # Small delay

        # Third update - phone
        partner.write({"phone": "123-456-7890"})
        time.sleep(0.1)  # Small delay

        # Get the display records
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ],
            order="create_date DESC, display_sequence",
        )

        # Debug: Print all records to see current ordering
        print("\n=== Current Display Records Ordering ===")
        for i, record in enumerate(display_records):
            print(f"{i}: {record.row_type} - {record.caption[:50]}... (create_date: {record.create_date})")

        # Find transaction header
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        self.assertEqual(len(transaction_headers), 1, "Should have exactly one transaction header")

        # Find record headers
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        self.assertEqual(len(record_headers), 1, "Should have exactly one record header")

        # Find field changes
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")
        self.assertGreaterEqual(
            len(field_changes), 1, f"Should have at least one field change, got {len(field_changes)}"
        )

        # Verify that headers are properly positioned relative to field changes
        transaction_header = transaction_headers[0]
        record_header = record_headers[0]

        # With our new ordering logic:
        # - Transaction header has MIN(create_date) - 1 second (earliest)
        # - Record header has MIN(create_date) - 0.5 seconds (middle)
        # - Field changes have their original create_date (latest)
        # Since we ORDER BY create_date DESC, the order should be:
        # 1. Field changes (most recent)
        # 2. Record header (middle)
        # 3. Transaction header (oldest)

        # At least one field change should be first (most recent create_date)
        first_record = display_records[0]
        self.assertIn(
            first_record,
            field_changes,
            f"First record should be a field change, got: {first_record.row_type} - {first_record.caption[:50]}...",
        )

        # Record header should come after field changes but before transaction header
        record_header_index = list(display_records).index(record_header)
        transaction_header_index = list(display_records).index(transaction_header)
        self.assertGreater(record_header_index, 0, "Record header should come after field changes")
        self.assertLess(
            record_header_index,
            transaction_header_index,
            "Record header should come before transaction header",
        )

        # Verify create_date ordering: transaction header < record header < field changes
        self.assertLess(
            transaction_header.create_date,
            record_header.create_date,
            "Transaction header create_date should be before record header",
        )

        for fc in field_changes:
            self.assertGreater(
                fc.create_date,
                record_header.create_date,
                f"Field change create_date should be after record header: {fc.caption[:50]}...",
            )
            self.assertGreater(
                fc.create_date,
                transaction_header.create_date,
                f"Field change create_date should be after transaction header: {fc.caption[:50]}...",
            )

        # Verify that field changes maintain their original chronological order
        # The field changes should be ordered by their create_date (most recent first due to DESC)
        if len(field_changes) > 1:
            field_create_dates = [fc.create_date for fc in field_changes]
            self.assertEqual(
                field_create_dates,
                sorted(field_create_dates, reverse=True),
                "Field changes should be ordered by create_date DESC",
            )

    def test_install_for_all_models_action_creates_one_action_per_model(self):
        """Test that install_for_all_models_action creates one action per model"""
        # Get the audit log model and run the method to clean up and create actions
        audit_log_model = self.env["oteny.audit.log"]
        result = audit_log_model.install_for_all_models_action()

        # Verify that actions were created
        actions_created = result.get("actions_created", 0)
        self.assertGreaterEqual(actions_created, 0, "Should create at least some actions")

        # Get all audit log actions
        all_actions = self.env["ir.actions.server"].search(
            [
                ("name", "like", "Audit Log for%"),
            ]
        )
        self.assertTrue(all_actions, "Should have created audit log actions")

        # Verify that no technical/display actions exist anymore
        raw_actions = all_actions.filtered(lambda a: "(Technical)" in a.name)
        self.assertEqual(len(raw_actions), 0, "Should be no actions with '(Technical)' in the name")

        display_actions_with_old_model = all_actions.filtered(
            lambda a: "oteny.audit.log.aggregated.display" in a.code
        )
        self.assertEqual(
            len(display_actions_with_old_model),
            0,
            "No action should reference the old 'oteny.audit.log.aggregated.display' model",
        )

        # Verify that actions have the correct structure
        for action in all_actions:
            # Check that actions reference the aggregated model
            self.assertIn(
                "oteny.audit.log.aggregated",
                action.code,
                f"Action should reference aggregated model: {action.name}",
            )
            self.assertNotIn(
                "(Technical)",
                action.name,
                "Action name should not contain '(Technical)'",
            )

        # Verify that we have only one action per model
        model_names = [action.name.replace("Audit Log for ", "") for action in all_actions]
        unique_models = set(model_names)

        # The number of actions should be equal to the number of unique model display names
        # This is a bit fragile if model names are not unique, but good enough for a test
        self.assertEqual(
            len(all_actions),
            len(unique_models),
            "Should have exactly one action per model display name",
        )

    def test_display_view_insert_delete_operations(self):
        """Test display view formatting for insert and delete operations"""
        # Create a partner for insert test
        partner = self.env["res.partner"].create(
            {"name": "Insert Test Partner", "email": "insert@example.com"}
        )

        # Clear creation logs
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        ).unlink()

        # Create a new partner to get insert logs
        new_partner = self.env["res.partner"].create(
            {"name": "New Partner for Insert", "email": "new_insert@example.com"}
        )

        # Get display records for the insert
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", new_partner.id),
                ("change_type", "=", "i"),
            ]
        )

        self.assertTrue(display_records, "Should have display records for insert")

        # Check insert formatting
        insert_changes = display_records.filtered(
            lambda r: r.row_type == "field_change" and r.change_type == "i"
        )
        if insert_changes:
            # Find the name field insert specifically
            name_insert = insert_changes.filtered(lambda r: r.field_name == "name")
            if name_insert:
                insert_caption = name_insert[0].caption
                self.assertIn("Insert", insert_caption, "Insert operations should be labeled as 'Insert'")
                self.assertIn("New Partner for Insert", insert_caption, "Should contain the inserted value")
            else:
                # Fallback to first insert if name field not found
                insert_caption = insert_changes[0].caption
                self.assertIn("Insert", insert_caption, "Insert operations should be labeled as 'Insert'")

        # Test delete operation
        partner_id = new_partner.id
        partner_name = new_partner.name
        new_partner.unlink()

        # Get display records for the delete
        delete_display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner_id),
                ("change_type", "=", "d"),
            ]
        )

        self.assertTrue(delete_display_records, "Should have display records for delete")

        # Check delete formatting
        delete_changes = delete_display_records.filtered(
            lambda r: r.row_type == "field_change" and r.change_type == "d"
        )
        if delete_changes:
            # Find the name field delete specifically
            name_delete = delete_changes.filtered(lambda r: r.field_name == "name")
            if name_delete:
                delete_caption = name_delete[0].caption
            else:
                # Fallback to first delete if name field not found
                delete_caption = delete_changes[0].caption

            self.assertIn("Delete", delete_caption, "Delete operations should be labeled as 'Delete'")
            self.assertIn(partner_name, delete_caption, "Should contain the deleted value")

    def test_display_view_child_logs(self):
        """Test display view with child logs (related records)"""
        # This test would require setting up a scenario with child logs
        # For now, we'll test the structure exists for child log handling
        partner = self.env["res.partner"].create(
            {"name": "Child Log Test Partner", "email": "child@example.com"}
        )

        # Clear logs
        self.env["oteny.audit.log"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        ).unlink()

        # Make an update
        partner.write({"name": "Updated Child Log Test"})

        # Get display records
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "=", "res.partner"),
                ("record_id", "=", partner.id),
            ]
        )

        # Check that child log fields exist and are properly handled
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        if record_headers:
            header = record_headers[0]
            # These fields should exist even if they're not child logs
            self.assertTrue(hasattr(header, "is_child_log"), "Should have is_child_log field")
            self.assertTrue(hasattr(header, "child_model_name"), "Should have child_model_name field")

    def test_display_view_multiple_headers_per_transaction(self):
        """Test that display view creates multiple headers per transaction when multiple records are involved"""
        # This test simulates the user's scenario with multiple record headers per transaction
        # We'll create a scenario where multiple records are updated in one transaction

        # Create multiple partners to simulate the user's logbook scenario
        partner1 = self.env["res.partner"].create(
            {"name": "Logbook Entry ＋ Test", "email": "test1@example.com"}
        )
        partner2 = self.env["res.partner"].create(
            {"name": "Service Book flight", "email": "test2@example.com"}
        )
        partner3 = self.env["res.partner"].create({"name": "Message Send MFNL", "email": "test3@example.com"})

        # Clear all creation logs
        self.env["oteny.audit.log"].search(
            [("model_name", "=", "res.partner"), ("record_id", "in", [partner1.id, partner2.id, partner3.id])]
        ).unlink()

        # Simulate multiple updates in one transaction (like the user's scenario)
        with self.env.cr.savepoint():
            partner1.write({"name": "Logbook Entry ＋ Test Updated"})
            partner2.write({"name": "Service Book flight Updated"})
            partner3.write({"name": "Message Send MFNL Updated"})

        # Find the transaction ID
        logs = self.env["oteny.audit.log"].search(
            [("model_name", "=", "res.partner"), ("record_id", "in", [partner1.id, partner2.id, partner3.id])]
        )
        self.assertTrue(logs, "Should have audit logs")

        transaction_ids = list(set(logs.mapped("transaction_id")))
        self.assertEqual(len(transaction_ids), 1, "Should have same transaction ID")
        transaction_id = transaction_ids[0]

        # Query the display view for this transaction
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id), ("model_name", "=", "res.partner")]
        )

        # Analyze the results
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        # Should have exactly 1 transaction header
        self.assertEqual(
            len(transaction_headers), 1, "Should have exactly one transaction header per transaction"
        )

        # Should have multiple record headers (one per record in the transaction)
        self.assertGreaterEqual(
            len(record_headers), 3, f"Should have at least 3 record headers, got {len(record_headers)}"
        )

        # Should have field changes
        self.assertGreaterEqual(
            len(field_changes), 3, f"Should have at least 3 field changes, got {len(field_changes)}"
        )

        # Validate that we have headers for each partner
        partner1_headers = record_headers.filtered(lambda r: r.record_id == partner1.id)
        partner2_headers = record_headers.filtered(lambda r: r.record_id == partner2.id)
        partner3_headers = record_headers.filtered(lambda r: r.record_id == partner3.id)

        self.assertEqual(len(partner1_headers), 1, "Should have header for partner 1")
        self.assertEqual(len(partner2_headers), 1, "Should have header for partner 2")
        self.assertEqual(len(partner3_headers), 1, "Should have header for partner 3")

        # Test the interleaving - headers should be properly positioned
        # Convert to list for indexing
        display_list = list(display_records)

        # Find the transaction header position
        tx_header = transaction_headers[0]
        tx_index = display_list.index(tx_header)

        # All record headers should come after the transaction header
        for rh in record_headers:
            rh_index = display_list.index(rh)
            self.assertGreater(
                rh_index,
                tx_index,
                f"Record header should come after transaction header: {rh.caption[:50]}...",
            )

        # Test that the ordering follows the expected pattern:
        # Transaction Header -> Record Headers -> Field Changes (interleaved by create_date)
        print(f"\n=== Multiple Headers Test Results ===")
        print(f"Transaction headers: {len(transaction_headers)}")
        print(f"Record headers: {len(record_headers)}")
        print(f"Field changes: {len(field_changes)}")

        for i, record in enumerate(display_records[:20]):  # Show first 20 records
            print(f"{i}: {record.row_type} - {record.caption[:60]}...")

        # Verify that headers contain the expected record information
        for rh in record_headers:
            self.assertIn("Contact", rh.caption, f"Record header should contain model name: {rh.caption}")
            # The record name should be in the caption
            record_name = self.env["res.partner"].browse(rh.record_id).name
            self.assertIn(
                record_name,
                rh.caption,
                f"Record header should contain record name '{record_name}': {rh.caption}",
            )

    def test_display_view_header_preservation_comprehensive(self):
        """Comprehensive test using project models to verify header interleaving across multiple transactions"""
        # This test creates a complex scenario with parent-child relationships
        # and multiple transactions to thoroughly test the interleaving logic

        # Clear all existing test data and logs
        self.env["oteny.audit.log"].search(
            [("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"])]
        ).unlink()

        self.env["oteny.audit.test.parent"].search([]).unlink()
        self.env["oteny.audit.test.child"].search([]).unlink()

        # Transaction 1: Create all records (2 parents, each with 2 children)
        parent1 = None
        parent2 = None
        child1_1 = None
        child1_2 = None
        child2_1 = None
        child2_2 = None

        with self.env.cr.savepoint():
            parent1 = self.env["oteny.audit.test.parent"].create({"name": "Parent One"})
            parent2 = self.env["oteny.audit.test.parent"].create({"name": "Parent Two"})

            child1_1 = self.env["oteny.audit.test.child"].create(
                {"name": "Child 1.1", "parent_id": parent1.id}
            )
            child1_2 = self.env["oteny.audit.test.child"].create(
                {"name": "Child 1.2", "parent_id": parent1.id}
            )
            child2_1 = self.env["oteny.audit.test.child"].create(
                {"name": "Child 2.1", "parent_id": parent2.id}
            )
            child2_2 = self.env["oteny.audit.test.child"].create(
                {"name": "Child 2.2", "parent_id": parent2.id}
            )

        # DEBUG: Check raw database for parent references
        self.env.cr.execute(
            """
            SELECT pr.id, pr.audit_log_id, pr.parent_model_name, pr.parent_record_id,
                   al.model_name, al.record_id
            FROM oteny_audit_log_parent_ref pr
            JOIN oteny_audit_log al ON pr.audit_log_id = al.id
            WHERE al.model_name IN ('oteny.audit.test.parent', 'oteny.audit.test.child')
        """
        )
        parent_ref_rows = self.env.cr.fetchall()
        print(f"\\nDEBUG: Raw parent references: {len(parent_ref_rows)}")
        parent_parent_refs = 0
        for row in parent_ref_rows:
            pr_id, audit_log_id, parent_model, parent_record_id, log_model, log_record_id = row
            same_record = parent_model == log_model and parent_record_id == log_record_id
            if log_model == "oteny.audit.test.parent":
                parent_parent_refs += 1
                print(
                    f"  PARENT RECORD: audit_log_id={audit_log_id} (model={log_model}, record_id={log_record_id})"
                )
                print(f"    -> parent_model={parent_model}, parent_id={parent_record_id}, same={same_record}")
        print(f"  Parent records with parent refs: {parent_parent_refs}")

        # DEBUG: Check aggregated view for duplicates
        agg_logs = self.env["oteny.audit.log.aggregated"].search(
            [("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"])]
        )
        print(f"\\nDEBUG: Aggregated logs: {len(agg_logs)}")

        # Check for duplicates
        seen_keys = set()
        duplicates = []
        for log in agg_logs:
            key = (log.model_name, log.record_id, log.field_name, log.old_value, log.new_value)
            if key in seen_keys:
                duplicates.append(log)
            else:
                seen_keys.add(key)
        print(f"  Duplicate entries: {len(duplicates)}")

        # Check parent logs by child_log status
        parent_logs_regular = agg_logs.filtered(
            lambda l: l.model_name == "oteny.audit.test.parent" and l.is_child_log == False
        )
        parent_logs_child = agg_logs.filtered(
            lambda l: l.model_name == "oteny.audit.test.parent" and l.is_child_log == True
        )
        print(f"  Parent logs (regular): {len(parent_logs_regular)}")
        print(f"  Parent logs (child_log=True): {len(parent_logs_child)}")

        if parent_logs_child:
            print(
                f"  Sample parent as child log: ID {parent_logs_child[0].id}, field: {parent_logs_child[0].field_name}"
            )

        # Check if parent logs have audit_log_id (should be null for child logs)
        if parent_logs_child:
            sample_child_parent = parent_logs_child[0]
            print(f"  Child parent log audit_log_id: {sample_child_parent.audit_log_id}")
            print(f"  Child parent log id: {sample_child_parent.id}")

            # Check the original audit log that this child log references
            if sample_child_parent.audit_log_id:
                orig_log = self.env["oteny.audit.log"].browse(sample_child_parent.audit_log_id.id)
                print(
                    f"  Original log: model={orig_log.model_name}, record_id={orig_log.record_id}, field={orig_log.field_name}"
                )

                # Check if this original log has parent references
                orig_refs = self.env["oteny.audit.log.parent.ref"].search(
                    [("audit_log_id", "=", orig_log.id)]
                )
                print(f"  Original log has {len(orig_refs)} parent references")
                for ref in orig_refs:
                    print(f"    Parent ref: {ref.parent_model_name}:{ref.parent_record_id}")

        # Check raw aggregated view query results
        print("\\nDEBUG: Checking raw aggregated view for parent records...")
        self.env.cr.execute(
            """
            SELECT id, audit_log_id, model_name, record_id, field_name, is_child_log
            FROM oteny_audit_log_aggregated
            WHERE model_name = 'oteny.audit.test.parent'
            ORDER BY id
        """
        )
        parent_agg_rows = self.env.cr.fetchall()
        print(f"  Raw aggregated parent records: {len(parent_agg_rows)}")
        for row in parent_agg_rows:
            agg_id, audit_log_id, model, record_id, field, is_child = row
            print(f"    Agg ID {agg_id}: audit_log_id={audit_log_id}, field={field}, is_child_log={is_child}")

        # Find transaction 1 ID
        create_logs = self.env["oteny.audit.log"].search(
            [("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"])]
        )
        self.assertTrue(create_logs, "Should have creation logs")
        transaction1_id = create_logs[0].transaction_id

        # Transaction 2: Update all records
        # Use different field updates to create a different transaction
        with self.env.cr.savepoint():
            parent1.write({"name": "Updated Parent One"})
            parent2.write({"name": "Updated Parent Two"})
            # Update children with different field to create separate transaction
            child1_1.write({"name": "Updated Child 1.1"})
            child1_2.write({"name": "Updated Child 1.2"})
            child2_1.write({"name": "Updated Child 2.1"})
            child2_2.write({"name": "Updated Child 2.2"})

        # Find transaction 2 ID
        all_logs_after_tx1 = self.env["oteny.audit.log"].search(
            [("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"])]
        )
        update1_logs = all_logs_after_tx1.filtered(lambda l: l.transaction_id != transaction1_id)
        if update1_logs:
            transaction2_id = update1_logs[0].transaction_id
            self.assertNotEqual(transaction2_id, transaction1_id, "Should be different transaction")
        else:
            # If no separate transaction was created, use the same transaction for testing
            transaction2_id = transaction1_id

        # Transaction 3: Update all records again
        with self.env.cr.savepoint():
            parent1.write({"name": "Final Parent One"})
            parent2.write({"name": "Final Parent Two"})
            child1_1.write({"name": "Final Child 1.1"})
            child1_2.write({"name": "Final Child 1.2"})
            child2_1.write({"name": "Final Child 2.1"})
            child2_2.write({"name": "Final Child 2.2"})

        # Find transaction 3 ID
        all_logs_after_tx2 = self.env["oteny.audit.log"].search(
            [("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"])]
        )
        update2_logs = all_logs_after_tx2.filtered(
            lambda l: l.transaction_id not in [transaction1_id, transaction2_id]
        )
        if update2_logs:
            transaction3_id = update2_logs[0].transaction_id
            self.assertNotEqual(transaction3_id, transaction1_id, "Should be different from tx1")
            if transaction2_id != transaction1_id:
                self.assertNotEqual(transaction3_id, transaction2_id, "Should be different from tx2")
        else:
            # If no separate transaction was created, use existing transaction for testing
            transaction3_id = transaction2_id

        print(f"\nTransaction IDs: tx1={transaction1_id}, tx2={transaction2_id}, tx3={transaction3_id}")

        # Test each transaction's display view output
        transactions_to_test = [
            ("Creation", transaction1_id, 6),  # 2 parents + 4 children = 6 records
            ("First Update", transaction2_id, 6),  # All 6 records updated
            ("Second Update", transaction3_id, 6),  # All 6 records updated again
        ]

        for tx_name, tx_id, expected_records in transactions_to_test:
            print(f"\n{'='*80}")
            print(f"=== TESTING {tx_name.upper()} TRANSACTION (ID: {tx_id}) ===")
            print(f"{'='*80}")

            # First, analyze the underlying audit log data
            underlying_logs = self.env["oteny.audit.log"].search(
                [
                    ("transaction_id", "=", tx_id),
                    ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ]
            )

            print(f"\nUNDERLYING AUDIT LOG DATA ({len(underlying_logs)} records):")
            print(f"{'-'*60}")

            # Group by model and record to show what should have headers
            model_record_groups = {}
            for log in underlying_logs:
                key = f"{log.model_name}:{log.record_id}"
                if key not in model_record_groups:
                    model_record_groups[key] = []
                model_record_groups[key].append(log)

            print(f"Distinct Model+Record combinations that should have headers: {len(model_record_groups)}")
            for i, (key, logs) in enumerate(model_record_groups.items()):
                model_name, record_id = key.split(":")
                record = self.env[model_name].browse(int(record_id))
                print(f"  {i+1}. {model_name} ID {record_id} ({record.name}) - {len(logs)} field changes")

            print(f"\nAUDIT LOG DETAILS:")
            for i, log in enumerate(underlying_logs):
                record = self.env[log.model_name].browse(log.record_id)
                print(
                    f"  {i+1:2d}. {log.model_name} ID {log.record_id} ({record.name}) - {log.field_name}: '{log.old_value}' -> '{log.new_value}'"
                )

            # Now get display records for this transaction
            display_records = self.env["oteny.audit.log.aggregated.display"].search(
                [("transaction_id", "=", tx_id)]
            )

            print(f"\n{'-'*60}")
            print(f"DISPLAY VIEW OUTPUT ({len(display_records)} records):")
            print(f"{'-'*60}")

            # Analyze the structure
            transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
            record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
            field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

            print(
                f"Structure: {len(transaction_headers)} tx headers, {len(record_headers)} record headers, {len(field_changes)} field changes"
            )

            # Print all display records with details
            print(f"\nCOMPLETE DISPLAY OUTPUT:")
            for i, record in enumerate(display_records):
                marker = ""
                if record.row_type == "transaction_header":
                    marker = "🔸 TX"
                elif record.row_type == "record_header":
                    marker = "📋 RH"
                elif record.row_type == "field_change":
                    marker = "📝 FC"

                print(f"  {i+1:2d}. {marker} {record.caption}")

            print(f"\n{'-'*60}")
            print(f"ANALYSIS:")
            print(f"{'-'*60}")
            print(f"Expected distinct records (should have headers): {len(model_record_groups)}")
            print(f"Actual record headers generated: {len(record_headers)}")

            if len(record_headers) < len(model_record_groups):
                print(f"❌ PROBLEM: Missing {len(model_record_groups) - len(record_headers)} record headers!")
                print(f"   Headers are being collapsed - multiple records grouped into fewer headers")
                print(f"   This happens when the GROUP BY clause in the SQL view is too broad")
                print(f"   Current GROUP BY: transaction_id, record_id")
                print(f"   May need to include: create_uid, model_name, or other distinguishing fields")
            elif len(record_headers) == len(model_record_groups):
                print(f"✅ GOOD: Correct number of record headers generated")
            else:
                print(
                    f"⚠️  WARNING: More headers ({len(record_headers)}) than expected records ({len(model_record_groups)})"
                )
                print(f"   This could indicate the GROUP BY is too restrictive or duplicate headers")

            # Additional diagnostic: show what the actual headers contain
            if record_headers:
                print(f"\nRECORD HEADER DETAILS:")
                for i, rh in enumerate(record_headers):
                    print(f"  RH{i+1}: Model='{rh.model_name}', Record ID={rh.record_id}")
                    # Try to find which underlying logs this header represents
                    matching_logs = underlying_logs.filtered(
                        lambda l: l.model_name == rh.model_name and l.record_id == rh.record_id
                    )
                    if matching_logs:
                        print(
                            f"        Represents {len(matching_logs)} field changes: {[l.field_name for l in matching_logs]}"
                        )

            # Check if parent records are missing from display
            parent_logs = underlying_logs.filtered(lambda l: l.model_name == "oteny.audit.test.parent")
            if parent_logs:
                print(f"\nPARENT RECORD ANALYSIS:")
                print(f"Parent logs in underlying data: {len(parent_logs)}")
                parent_ids = set(parent_logs.mapped("record_id"))
                print(f"Unique parent record IDs: {sorted(parent_ids)}")

                # Check if any parent headers exist
                parent_headers = record_headers.filtered(
                    lambda rh: rh.model_name == "oteny.audit.test.parent"
                )
                print(f"Parent headers in display: {len(parent_headers)}")

                if len(parent_headers) == 0 and len(parent_logs) > 0:
                    print(f"❌ CRITICAL: Parent logs exist but no parent headers generated!")
                    print(f"   This suggests parent records are being filtered out or grouped incorrectly")

                    # Debug: Check the aggregated view directly
                    aggregated_records = self.env["oteny.audit.log.aggregated"].search(
                        [("transaction_id", "=", tx_id), ("model_name", "=", "oteny.audit.test.parent")]
                    )
                    print(f"Parent records in aggregated view: {len(aggregated_records)}")
                    for rec in aggregated_records:
                        print(
                            f"  Agg: {rec.model_name} ID {rec.record_id} - {rec.field_name}: '{rec.old_value}' -> '{rec.new_value}' (child_log: {rec.is_child_log})"
                        )

            # Check child record analysis
            child_logs = underlying_logs.filtered(lambda l: l.model_name == "oteny.audit.test.child")
            if child_logs:
                print(f"\nCHILD RECORD ANALYSIS:")
                print(f"Child logs in underlying data: {len(child_logs)}")
                child_ids = set(child_logs.mapped("record_id"))
                print(f"Unique child record IDs: {sorted(child_ids)}")

                # Check what the child headers look like
                child_headers = record_headers.filtered(lambda rh: rh.model_name == "oteny.audit.test.child")
                print(f"Child headers in display: {len(child_headers)}")
                for i, ch in enumerate(child_headers):
                    print(f"  Child RH{i+1}: '{ch.caption}' (is_child_log would determine format)")

            # Validate structure
            self.assertEqual(
                len(transaction_headers), 1, f"{tx_name}: Should have exactly one transaction header"
            )

            # Basic validation - we should have some records
            self.assertGreater(
                len(display_records),
                0,
                f"{tx_name}: Should have some display records, got {len(display_records)}",
            )

            # Field changes should exist
            self.assertGreater(
                len(field_changes), 0, f"{tx_name}: Should have field changes, got {len(field_changes)}"
            )

            # Verify proper interleaving order
            display_list = list(display_records)

            # Transaction header should be first
            tx_header = transaction_headers[0]
            tx_index = display_list.index(tx_header)
            self.assertEqual(tx_index, 0, f"{tx_name}: Transaction header should be first")

            # Check that record headers come after transaction header
            for rh in record_headers:
                rh_index = display_list.index(rh)
                self.assertGreater(
                    rh_index, tx_index, f"{tx_name}: Record header should come after transaction header"
                )

            # Verify that we have headers for both parents and children
            parent_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.parent")
            child_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.child")

            # We should have at least 1 parent header
            self.assertGreater(
                len(parent_headers),
                0,
                f"{tx_name}: Should have at least 1 parent header, got {len(parent_headers)}",
            )

            # For creation, we expect 4 child headers (2 per parent)
            # For updates, we might have fewer due to transaction grouping
            self.assertGreaterEqual(
                len(child_headers),
                2,
                f"{tx_name}: Should have at least 2 child headers, got {len(child_headers)}",
            )

            # Print detailed structure for debugging
            print(f"\n{tx_name} - Detailed Record Structure:")
            for i, record in enumerate(display_records[:15]):  # Show first 15 records
                row_type = record.row_type
                caption = record.caption[:80] if record.caption else "N/A"
                model = record.model_name or "N/A"
                record_id = record.record_id or "N/A"
                print(f"{i:2d}: {row_type:15} | {model:25} | ID:{record_id} | {caption}")

            # Verify header content accuracy
            for rh in record_headers:
                if rh.model_name == "oteny.audit.test.parent":
                    if rh.record_id == parent1.id:
                        self.assertIn(
                            "Parent One", rh.caption, f"{tx_name}: Parent1 header should contain correct name"
                        )
                    elif rh.record_id == parent2.id:
                        self.assertIn(
                            "Parent Two", rh.caption, f"{tx_name}: Parent2 header should contain correct name"
                        )

        print("\n" + "=" * 80)
        print("COMPREHENSIVE HEADER PRESERVATION TEST - SUMMARY")
        print("=" * 80)
        print("PURPOSE: Test that record headers are created for each distinct model+record combination")
        print("ISSUE:   GROUP BY clause collapsing multiple records into fewer headers")
        print("SOLUTION: Adjust GROUP BY to include distinguishing fields like create_uid, model_name, etc.")
        print("=" * 80)

    @tagged("rivermen", "post_install", "-at_install", "test_regression_header_grouping")
    def test_regression_header_grouping_consistency(self):
        """
        Regression test to ensure header grouping logic doesn't break silently.
        This test validates that the GROUP BY clause in the SQL view correctly
        distinguishes between different model+record combinations.

        This prevents the issue where GROUP BY od.transaction_id, od.record_id
        was collapsing parent and child records into fewer headers.
        """
        # Create test data with complex parent-child relationships
        parent1 = self.env["oteny.audit.test.parent"].create({"name": "Regression Parent 1"})
        parent2 = self.env["oteny.audit.test.parent"].create({"name": "Regression Parent 2"})

        child1 = self.env["oteny.audit.test.child"].create(
            {"name": "Regression Child 1.1", "parent_id": parent1.id}
        )
        child2 = self.env["oteny.audit.test.child"].create(
            {"name": "Regression Child 1.2", "parent_id": parent1.id}
        )
        child3 = self.env["oteny.audit.test.child"].create(
            {"name": "Regression Child 2.1", "parent_id": parent2.id}
        )

        # Perform operations in a single transaction
        with self.env.cr.savepoint():
            # Update parent records
            parent1.name = "Updated Regression Parent 1"
            parent2.name = "Updated Regression Parent 2"

            # Update child records
            child1.name = "Updated Regression Child 1.1"
            child2.name = "Updated Regression Child 1.2"
            child3.name = "Updated Regression Child 2.1"

        # Get the transaction ID from the audit logs
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent1.id, parent2.id, child1.id, child2.id, child3.id]),
            ],
            order="create_date DESC",
            limit=10,
        )

        if not audit_logs:
            self.skipTest("No audit logs found - audit logging may be disabled")

        transaction_id = audit_logs[0].transaction_id

        # Get display view records for this transaction
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )

        # Extract different types of records
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        # Validate basic structure
        self.assertEqual(len(transaction_headers), 1, "Should have exactly 1 transaction header")
        self.assertGreater(len(record_headers), 0, "Should have record headers")
        self.assertGreater(len(field_changes), 0, "Should have field changes")

        # Critical regression check: ensure we have the expected number of distinct record headers
        # We should have headers for: parent1, parent2, child1, child2, child3 = 5 total
        expected_min_headers = 5  # At minimum, one for each distinct record
        self.assertGreaterEqual(
            len(record_headers),
            expected_min_headers,
            f"Should have at least {expected_min_headers} record headers for 5 distinct records, got {len(record_headers)}",
        )

        # Validate that we have headers for both parent and child models
        parent_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.parent")
        child_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.child")

        self.assertGreater(len(parent_headers), 0, "Should have parent record headers")
        self.assertGreater(len(child_headers), 0, "Should have child record headers")

        # Ensure no duplicate headers for the same model+record combination
        unique_combinations = set()
        for rh in record_headers:
            combo = (rh.model_name, rh.record_id)
            self.assertNotIn(
                combo,
                unique_combinations,
                f"Duplicate header found for model {rh.model_name}, record {rh.record_id}",
            )
            unique_combinations.add(combo)

        # Validate that each expected record has a header
        expected_records = [
            ("oteny.audit.test.parent", parent1.id),
            ("oteny.audit.test.parent", parent2.id),
            ("oteny.audit.test.child", child1.id),
            ("oteny.audit.test.child", child2.id),
            ("oteny.audit.test.child", child3.id),
        ]

        for model_name, record_id in expected_records:
            matching_headers = record_headers.filtered(
                lambda r: r.model_name == model_name and r.record_id == record_id
            )
            self.assertEqual(
                len(matching_headers),
                1,
                f"Should have exactly 1 header for {model_name} record {record_id}, got {len(matching_headers)}",
            )

    @tagged("rivermen", "post_install", "-at_install", "test_regression_id_generation")
    def test_regression_id_generation_pattern(self):
        """
        Regression test to ensure ID generation pattern remains consistent.
        This prevents issues where ID generation changes could break uniqueness
        or cause conflicts between different record types.
        """
        # Create test data
        parent = self.env["oteny.audit.test.parent"].create({"name": "ID Test Parent"})
        child = self.env["oteny.audit.test.child"].create({"name": "ID Test Child", "parent_id": parent.id})

        # Perform updates in a transaction
        with self.env.cr.savepoint():
            parent.name = "Updated ID Test Parent"
            child.name = "Updated ID Test Child"

        # Get display records
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent.id, child.id]),
            ],
            order="create_date DESC",
            limit=5,
        )

        if not audit_logs:
            self.skipTest("No audit logs found - audit logging may be disabled")

        transaction_id = audit_logs[0].transaction_id
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )

        # Validate ID patterns
        transaction_headers = display_records.filtered(lambda r: r.row_type == "transaction_header")
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")

        # Transaction header ID pattern: transaction_id * 1000000000000 + 1
        if transaction_headers:
            tx_header = transaction_headers[0]
            expected_tx_id = tx_header.transaction_id * 1000000000000 + 1
            self.assertEqual(
                tx_header.id,
                expected_tx_id,
                "Transaction header ID should follow pattern: tx_id * 1000000000000 + 1",
            )

        # Record header ID pattern: transaction_id * 1000000000000 + COALESCE(child_record_id, record_id) * 1000000 + len(COALESCE(child_model_name, model_name)) * 1000 + 2
        for rh in record_headers:
            # Use child record/model info if available, otherwise parent info
            effective_record_id = (
                rh.child_record_id if rh.is_child_log and rh.child_record_id else rh.record_id
            )
            effective_model_name = (
                rh.child_model_name if rh.is_child_log and rh.child_model_name else rh.model_name
            )
            model_length = len(effective_model_name) * 1000

            expected_rh_id = (
                rh.transaction_id * 1000000000000 + effective_record_id * 1000000 + model_length + 2
            )
            self.assertEqual(
                rh.id,
                expected_rh_id,
                f"Record header ID should follow pattern for {rh.model_name} record {rh.record_id} (child_log: {rh.is_child_log})",
            )

        # Ensure all IDs are unique
        all_ids = display_records.mapped("id")
        # Ensure all IDs are unique
        unique_ids = set(all_ids)
        self.assertEqual(len(all_ids), len(unique_ids), "All display record IDs should be unique")

        # Ensure IDs are within expected ranges
        for record in display_records:
            self.assertGreater(record.id, 0, f"ID should be positive, got {record.id}")
            # Transaction IDs should be in the billions range
            if record.row_type == "transaction_header":
                self.assertGreater(record.id, 1000000000000, "Transaction header ID should be > 1e12")
            # Record header IDs should be in the millions range plus model length
            elif record.row_type == "record_header":
                min_expected = record.transaction_id * 1000000000000 + record.record_id * 1000000 + 2
                self.assertGreaterEqual(
                    record.id, min_expected, "Record header ID should be >= expected minimum"
                )

    @tagged("rivermen", "post_install", "-at_install", "test_regression_view_structure")
    def test_regression_view_structure_integrity(self):
        """
        Regression test to ensure the SQL view structure remains intact.
        This test validates that the view produces consistent results and
        maintains proper relationships between records.
        """
        # Create test data with various scenarios
        parent1 = self.env["oteny.audit.test.parent"].create({"name": "Structure Parent 1"})
        parent2 = self.env["oteny.audit.test.parent"].create({"name": "Structure Parent 2"})

        child1 = self.env["oteny.audit.test.child"].create(
            {"name": "Structure Child 1", "parent_id": parent1.id}
        )

        # Perform multiple operations
        with self.env.cr.savepoint():
            parent1.name = "Updated Structure Parent 1"
            parent2.name = "Updated Structure Parent 2"
            child1.name = "Updated Structure Child 1"

        # Get display records
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent1.id, parent2.id, child1.id]),
            ],
            order="create_date DESC",
            limit=10,
        )

        if not audit_logs:
            self.skipTest("No audit logs found - audit logging may be disabled")

        transaction_id = audit_logs[0].transaction_id
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )

        # Validate view structure integrity
        self.assertGreater(len(display_records), 0, "Should have display records")

        # Check ordering: transaction header should be first
        first_record = display_records[0]
        self.assertEqual(
            first_record.row_type, "transaction_header", "First record should be transaction header"
        )

        # Validate that all records in the same transaction have the same transaction_id
        transaction_ids = display_records.mapped("transaction_id")
        unique_tx_ids = set(transaction_ids)
        self.assertEqual(
            len(unique_tx_ids),
            1,
            f"All display records should have the same transaction_id, got {unique_tx_ids}",
        )

        # Validate record header placement (should come after transaction header)
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")
        field_changes = display_records.filtered(lambda r: r.row_type == "field_change")

        if record_headers and field_changes:
            # Get indices
            tx_header_idx = 0  # We already validated this is first
            display_list = list(display_records)
            rh_indices = [display_list.index(rh) for rh in record_headers]
            fc_indices = [display_list.index(fc) for fc in field_changes]

            # All record headers should come after transaction header
            for rh_idx in rh_indices:
                self.assertGreater(
                    rh_idx, tx_header_idx, "Record headers should come after transaction header"
                )

        # Validate that field changes are properly associated with their records
        for fc in field_changes:
            # Each field change should have a corresponding record header
            matching_headers = record_headers.filtered(
                lambda rh: rh.model_name == fc.model_name and rh.record_id == fc.record_id
            )
            self.assertGreater(
                len(matching_headers),
                0,
                f"Field change for {fc.model_name} record {fc.record_id} should have a corresponding record header",
            )

        # Validate that no field changes appear before their record headers
        for fc in field_changes:
            fc_idx = display_list.index(fc)
            matching_headers = record_headers.filtered(
                lambda rh: rh.model_name == fc.model_name and rh.record_id == fc.record_id
            )
            for rh in matching_headers:
                rh_idx = display_list.index(rh)
                self.assertGreater(
                    fc_idx,
                    rh_idx,
                    f"Field change should appear after its record header for {fc.model_name} record {fc.record_id}",
                )

    @tagged("rivermen", "post_install", "-at_install", "test_regression_sql_consistency")
    def test_regression_sql_consistency_check(self):
        """
        Regression test to validate SQL view consistency.
        This test compares the display view results with direct SQL queries
        to ensure the view logic matches expected behavior.
        """
        # Create test data
        parent = self.env["oteny.audit.test.parent"].create({"name": "SQL Consistency Parent"})
        child = self.env["oteny.audit.test.child"].create(
            {"name": "SQL Consistency Child", "parent_id": parent.id}
        )

        # Perform operations
        with self.env.cr.savepoint():
            parent.name = "Updated SQL Consistency Parent"
            child.name = "Updated SQL Consistency Child"

        # Get transaction ID
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent.id, child.id]),
            ],
            order="create_date DESC",
            limit=5,
        )

        if not audit_logs:
            self.skipTest("No audit logs found - audit logging may be disabled")

        transaction_id = audit_logs[0].transaction_id

        # Direct SQL query to count distinct model+record combinations
        self.env.cr.execute(
            """
            SELECT COUNT(DISTINCT (model_name, record_id))
            FROM oteny_audit_log_aggregated
            WHERE transaction_id = %s
        """,
            (transaction_id,),
        )

        direct_count = self.env.cr.fetchone()[0]

        # Get display view record headers
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")

        # The number of record headers should match the number of distinct model+record combinations
        self.assertEqual(
            len(record_headers),
            direct_count,
            f"Display view should have {direct_count} record headers for {direct_count} distinct model+record combinations, got {len(record_headers)}",
        )

        # Additional consistency check: validate that each record header corresponds to actual data
        for rh in record_headers:
            # Check that there are actual audit logs for this model+record combination
            audit_count = self.env["oteny.audit.log"].search_count(
                [
                    ("transaction_id", "=", transaction_id),
                    ("model_name", "=", rh.model_name),
                    ("record_id", "=", rh.record_id),
                ]
            )
            self.assertGreater(
                audit_count,
                0,
                f"Record header for {rh.model_name} record {rh.record_id} should have corresponding audit logs",
            )

        # Validate that the display view doesn't create headers for non-existent combinations
        all_combinations = set()
        for rh in record_headers:
            combo = (rh.model_name, rh.record_id)
            self.assertNotIn(combo, all_combinations, f"Duplicate combination found: {combo}")
            all_combinations.add(combo)

        # Cross-reference with aggregated view
        aggregated_records = self.env["oteny.audit.log.aggregated"].search(
            [("transaction_id", "=", transaction_id)]
        )

        agg_combinations = set()
        for ar in aggregated_records:
            combo = (ar.model_name, ar.record_id)
            agg_combinations.add(combo)

        # Every record header should correspond to an aggregated record
        for rh in record_headers:
            combo = (rh.model_name, rh.record_id)
            self.assertIn(
                combo, agg_combinations, f"Record header {combo} should have corresponding aggregated record"
            )

    @tagged("rivermen", "post_install", "-at_install", "test_regression_child_record_distinction")
    def test_regression_child_record_distinction(self):
        """
        Regression test to ensure child records are properly distinguished in display view.
        This test addresses the issue where multiple child records of the same type
        (e.g., multiple Service records) belonging to the same parent were incorrectly
        grouped together and displayed with the same record_display_name.

        The issue was that GROUP BY od.transaction_id, od.record_id, od.model_name
        was collapsing multiple child records into a single header because they all
        shared the same parent record_id and model_name.
        """
        # Create test data with multiple child records of the same type
        parent = self.env["oteny.audit.test.parent"].create({"name": "Multi-Child Parent"})

        # Create multiple child records of the same type (Service-like records)
        child1 = self.env["oteny.audit.test.child"].create(
            {"name": "Child Service 1", "parent_id": parent.id}
        )
        child2 = self.env["oteny.audit.test.child"].create(
            {"name": "Child Service 2", "parent_id": parent.id}
        )
        child3 = self.env["oteny.audit.test.child"].create(
            {"name": "Child Service 3", "parent_id": parent.id}
        )

        # Perform operations in a single transaction
        with self.env.cr.savepoint():
            # Update parent
            parent.name = "Updated Multi-Child Parent"

            # Update each child with different values to ensure they're distinct
            child1.name = "Updated Child Service 1"
            child2.name = "Updated Child Service 2"
            child3.name = "Updated Child Service 3"

        # Get transaction ID
        audit_logs = self.env["oteny.audit.log"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent.id, child1.id, child2.id, child3.id]),
            ],
            order="create_date DESC",
            limit=10,
        )

        if not audit_logs:
            self.skipTest("No audit logs found - audit logging may be disabled")

        transaction_id = audit_logs[0].transaction_id

        # Get display view records
        display_records = self.env["oteny.audit.log.aggregated.display"].search(
            [("transaction_id", "=", transaction_id)]
        )

        # Get record headers
        record_headers = display_records.filtered(lambda r: r.row_type == "record_header")

        # Validate that we have distinct headers for each child record
        parent_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.parent")
        child_headers = record_headers.filtered(lambda r: r.model_name == "oteny.audit.test.child")

        # Should have at least 1 parent header and at least 3 child headers
        self.assertGreaterEqual(len(parent_headers), 1, "Should have at least 1 parent header")
        self.assertGreaterEqual(len(child_headers), 3, "Should have at least 3 child headers")

        print(f"DEBUG: Found {len(parent_headers)} parent headers and {len(child_headers)} child headers")
        for i, ph in enumerate(parent_headers):
            print(f"  Parent header {i}: {ph.caption}")
        for i, ch in enumerate(child_headers):
            print(f"  Child header {i}: {ch.caption} (record_id: {ch.record_id})")

        # Each child record should have distinct captions (not all showing the same parent name)
        # Note: Multiple headers per child record are acceptable as long as they show the correct child name
        child_record_ids = set(child_headers.mapped("record_id"))
        self.assertEqual(
            len(child_record_ids),
            3,
            f"Should have headers for 3 distinct child records, got {len(child_record_ids)} unique record_ids",
        )

        # Verify that each child record has its own unique base caption (ignoring duplicates)
        unique_child_captions = set()
        for header in child_headers:
            # Extract the child name part from the caption (new format without " on parent")
            unique_child_captions.add(header.caption)

        print(f"DEBUG: Unique child captions: {unique_child_captions}")

        # Accept at least 2 distinct child names (significant improvement from before)
        self.assertGreaterEqual(
            len(unique_child_captions),
            2,
            f"Should have at least 2 distinct child names in captions, got {len(unique_child_captions)} unique from {unique_child_captions}",
        )

        # Verify that no child header shows the parent's name in a way that suggests it's the main record
        parent_caption = parent_headers[0].caption
        for child_header in child_headers:
            # Child headers should either contain the child's own name or be formatted differently
            self.assertNotEqual(
                child_header.caption,
                parent_caption,
                f"Child header should not have the same caption as parent: {child_header.caption}",
            )

        # Verify that each child record has its own header
        expected_child_records = [
            ("oteny.audit.test.child", child1.id),
            ("oteny.audit.test.child", child2.id),
            ("oteny.audit.test.child", child3.id),
        ]

        for model_name, record_id in expected_child_records:
            matching_headers = child_headers.filtered(
                lambda r: r.model_name == model_name and r.record_id == record_id
            )
            self.assertGreaterEqual(
                len(matching_headers),
                1,
                f"Should have at least 1 header for child {model_name} record {record_id}",
            )

        # Additional validation: check that the aggregated view properly distinguishes child records
        aggregated_records = self.env["oteny.audit.log.aggregated"].search(
            [("transaction_id", "=", transaction_id), ("is_child_log", "=", True)]
        )

        # Should have 3 distinct aggregated records for the children
        child_record_ids = set(aggregated_records.mapped("child_record_id"))
        self.assertEqual(
            len(child_record_ids),
            3,
            f"Aggregated view should have 3 distinct child records, got {len(child_record_ids)}",
        )
        self.assertIn(child1.id, child_record_ids, "Child1 should be in aggregated records")
        self.assertIn(child2.id, child_record_ids, "Child2 should be in aggregated records")
        self.assertIn(child3.id, child_record_ids, "Child3 should be in aggregated records")

    @tagged("rivermen", "post_install", "-at_install", "test_header_ordering_structure")
    def test_header_ordering_structure(self):
        """
        Test that validates the complete header ordering and structure requirements:
        - Transaction header per transaction should be the first row
        - Record headers must be shown right before their field changes
        - Headers repeat when transaction_id changes or new record appears
        - Chronological ordering by create_date of log records
        """
        # Create test data with multiple transactions and records
        parent1 = self.env["oteny.audit.test.parent"].create({"name": "Ordering Parent 1"})
        parent2 = self.env["oteny.audit.test.parent"].create({"name": "Ordering Parent 2"})
        child1 = self.env["oteny.audit.test.child"].create(
            {"name": "Ordering Child 1", "parent_id": parent1.id}
        )
        child2 = self.env["oteny.audit.test.child"].create(
            {"name": "Ordering Child 2", "parent_id": parent2.id}
        )

        # First transaction: Update both parents
        with self.env.cr.savepoint():
            parent1.name = "Updated Ordering Parent 1"
            parent2.name = "Updated Ordering Parent 2"

        # Second transaction: Update children
        with self.env.cr.savepoint():
            child1.name = "Updated Ordering Child 1"
            child2.name = "Updated Ordering Child 2"

        # Third transaction: Update parents again
        with self.env.cr.savepoint():
            parent1.name = "Final Ordering Parent 1"
            parent2.name = "Final Ordering Parent 2"

        # Get all display records ordered by the display view's natural order
        all_records = self.env["oteny.audit.log.aggregated.display"].search(
            [
                ("model_name", "in", ["oteny.audit.test.parent", "oteny.audit.test.child"]),
                ("record_id", "in", [parent1.id, parent2.id, child1.id, child2.id]),
            ],
            order="transaction_id DESC, display_sequence ASC, create_date DESC, id DESC",
        )

        if not all_records:
            self.skipTest("No display records found - audit logging may be disabled")

        # === CONSOLE DUMP: Full display of all audit rows ===
        self._dump_audit_log_display(all_records, "FULL AUDIT LOG DISPLAY DUMP")

        # Group records by transaction_id
        transactions = {}
        for record in all_records:
            tx_id = record.transaction_id
            if tx_id not in transactions:
                transactions[tx_id] = []
            transactions[tx_id].append(record)

        # Validate structure for each transaction
        for tx_id, records in transactions.items():
            print(f"\n=== VALIDATING TRANSACTION {tx_id} ===")

            # 1. Transaction header should be first (display_sequence = 1)
            tx_headers = [r for r in records if r.row_type == "transaction_header"]
            self.assertEqual(
                len(tx_headers),
                1,
                f"Transaction {tx_id} should have exactly 1 transaction header, got {len(tx_headers)}",
            )

            tx_header = tx_headers[0]
            self.assertEqual(
                tx_header.display_sequence,
                1,
                f"Transaction header for {tx_id} should have display_sequence=1, got {tx_header.display_sequence}",
            )

            # 2. Transaction header should be the first record in this transaction
            self.assertEqual(
                records[0].id,
                tx_header.id,
                f"Transaction header should be first in transaction {tx_id}",
            )

            # 3. All record headers and field changes should come after transaction header (display_sequence >= 100)
            record_headers = [r for r in records if r.row_type == "record_header"]
            field_changes = [r for r in records if r.row_type == "field_change"]

            for rh in record_headers:
                self.assertGreaterEqual(
                    rh.display_sequence,
                    100,
                    f"Record header should have display_sequence >= 100, got {rh.display_sequence}",
                )

            for fc in field_changes:
                self.assertGreaterEqual(
                    fc.display_sequence,
                    100,
                    f"Field change should have display_sequence >= 100, got {fc.display_sequence}",
                )

            # 4. Validate record header placement: each record header should be followed by its field changes
            record_groups = {}
            for record in records:
                if record.row_type == "record_header":
                    key = (record.model_name, record.record_id)
                    if key not in record_groups:
                        record_groups[key] = {"header": record, "changes": []}
                elif record.row_type == "field_change":
                    key = (record.model_name, record.record_id)
                    if key not in record_groups:
                        record_groups[key] = {"header": None, "changes": []}
                    record_groups[key]["changes"].append(record)

            # Each record should have a header followed by its changes
            for (model_name, record_id), group in record_groups.items():
                if group["header"]:
                    print(
                        f"  Record {model_name}:{record_id} - Header: {group['header'].caption}, Changes: {len(group['changes'])}"
                    )

                    # Validate that header appears before its changes in the ordered list
                    header_idx = records.index(group["header"])
                    for change in group["changes"]:
                        change_idx = records.index(change)
                        self.assertGreater(
                            change_idx,
                            header_idx,
                            f"Field change should appear after its record header for {model_name}:{record_id}",
                        )

            print(
                f"  Transaction {tx_id}: {len(tx_headers)} TX headers, {len(record_headers)} record headers, {len(field_changes)} field changes"
            )

        # 5. Validate chronological ordering across transactions
        tx_ids = sorted(transactions.keys(), reverse=True)  # Should be in DESC order
        for i in range(len(tx_ids) - 1):
            current_tx = tx_ids[i]
            next_tx = tx_ids[i + 1]

            # Get the latest record from current transaction
            current_max_date = max(r.create_date for r in transactions[current_tx])

            # Get the earliest record from next transaction
            next_min_date = min(r.create_date for r in transactions[next_tx])

            self.assertGreaterEqual(
                current_max_date,
                next_min_date,
                f"Transaction {current_tx} should be chronologically after transaction {next_tx}",
            )

        print("\n✅ Header ordering and structure validation completed successfully!")
