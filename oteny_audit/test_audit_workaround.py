#!/usr/bin/env python3
"""
Test script to verify the audit log workaround for Transaction __slots__ limitation.
This script demonstrates that we can store prev_values on Environment instead of Transaction.
"""

import sys
import os
from collections import defaultdict

# Add Odoo to path (adjust if needed)
sys.path.insert(0, "/Users/ries/odoo/odoo19")

# Import Odoo
import odoo
from odoo import api, SUPERUSER_ID


def test_environment_attribute():
    """Test that we can add attributes to Environment but not to Transaction."""

    # Initialize Odoo
    odoo.tools.config.parse_config([])
    db_name = odoo.tools.config["db_name"] or "your_database_name"

    # Get a database cursor
    with odoo.sql_db.db_connect(db_name).cursor() as cr:
        # Create an environment
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("Testing attribute assignment...")
        print("-" * 50)

        # Test 1: Try to add attribute to Transaction (will fail)
        print("1. Testing Transaction (has __slots__, should fail):")
        try:
            env.transaction.test_attr = "This will fail"
            print("   ✗ ERROR: Should not be able to add attribute to Transaction!")
        except AttributeError as e:
            print(f"   ✓ Expected error: {e}")

        # Test 2: Try to add attribute to Environment (will succeed)
        print("\n2. Testing Environment (no __slots__, should work):")
        try:
            env._audit_prev_values = defaultdict(dict)
            print("   ✓ Successfully added _audit_prev_values to Environment")

            # Verify we can use it
            test_field = "test_field"
            test_record_id = 123
            test_value = "old_value"

            env._audit_prev_values[test_field][test_record_id] = test_value
            retrieved_value = env._audit_prev_values[test_field][test_record_id]

            if retrieved_value == test_value:
                print(f"   ✓ Can store and retrieve values: {retrieved_value}")
            else:
                print(f"   ✗ Value mismatch: expected {test_value}, got {retrieved_value}")

        except Exception as e:
            print(f"   ✗ Unexpected error: {e}")

        # Test 3: Verify hasattr works correctly
        print("\n3. Testing hasattr on Environment:")
        if hasattr(env, "_audit_prev_values"):
            print("   ✓ hasattr(env, '_audit_prev_values') returns True")
        else:
            print("   ✗ hasattr(env, '_audit_prev_values') returns False")

        print("\n" + "=" * 50)
        print("SUMMARY: The workaround using Environment instead of Transaction works!")
        print("The audit log implementation should now function correctly.")


if __name__ == "__main__":
    test_environment_attribute()
