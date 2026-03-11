from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_auto_add")
class TestAutoAddServiceDedup(TransactionCase):
    """Test that auto_add_services ignores inactive rules even when
    active_test=False leaks into the environment context.

    The ORM sets active_test=False during trigger traversal
    (models.py _modified -> _modified_triggers). This context can leak
    into compute methods, causing searches to return inactive records.
    The auto_add_services rule search must be immune to this leak.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Use res.partner as a simple subject model that exists everywhere
        cls.partner_model = cls.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )

        # Create a domain condition that matches partners with a specific name
        cls.auto_add_domain = cls.env["riverflow.auto.add.domain"].create(
            {
                "name": "Test domain for auto-add dedup",
                "applies_to_model_id": cls.partner_model.id,
                "domain": "[('name', 'ilike', 'AutoAddTestSubject')]",
            }
        )

        # Create a service template
        cls.service_template = cls.env["riverflow.service"].create(
            {
                "name": "Test Auto-Add Template",
                "is_this_a_template": True,
            }
        )

        # Create the auto-add rule
        cls.auto_add_rule = cls.env["riverflow.auto.add.service"].create(
            {
                "domain_id": cls.auto_add_domain.id,
                "service_template_id": cls.service_template.id,
            }
        )

        # Create a matching subject partner
        cls.subject_partner = cls.env["res.partner"].create(
            {"name": "AutoAddTestSubject"}
        )

    def _count_services_for_subject(self):
        return self.env["riverflow.service"].with_context(active_test=False).search_count(
            [
                ("res_id", "=", self.subject_partner.id),
                ("res_model", "=", "res.partner"),
                ("created_by_auto_add_service_id", "!=", False),
            ]
        )

    def test_auto_add_creates_service(self):
        """Baseline: auto_add_services creates a service for a matching subject."""
        AutoAdd = self.env["riverflow.auto.add.service"]
        subjects = self.subject_partner

        AutoAdd.auto_add_services(subjects)

        self.assertEqual(
            self._count_services_for_subject(),
            1,
            "auto_add_services should create exactly one service",
        )

    def test_auto_add_dedup_prevents_duplicate(self):
        """The dedup check prevents creating the same service twice."""
        AutoAdd = self.env["riverflow.auto.add.service"]
        subjects = self.subject_partner

        AutoAdd.auto_add_services(subjects)
        AutoAdd.auto_add_services(subjects)

        self.assertEqual(
            self._count_services_for_subject(),
            1,
            "Running auto_add_services twice should still produce one service",
        )

    def test_inactive_rule_ignored_with_active_test_false(self):
        """Deactivated rules must not create services, even when
        active_test=False leaks into the environment from the ORM's
        trigger traversal (the root cause of the A1 duplicate bug)."""
        AutoAdd = self.env["riverflow.auto.add.service"]
        subjects = self.subject_partner

        # Let the rule create the initial service
        AutoAdd.auto_add_services(subjects)
        self.assertEqual(self._count_services_for_subject(), 1)

        # Deactivate the rule (simulates the consolidation hook archiving the old rule)
        self.auto_add_rule.active = False

        # Simulate the ORM context leak: call auto_add_services with active_test=False
        AutoAdd.with_context(active_test=False).auto_add_services(subjects)

        self.assertEqual(
            self._count_services_for_subject(),
            1,
            "Inactive rule must not create a duplicate service even when "
            "active_test=False leaks into the context",
        )

    def test_inactive_rule_ignored_with_second_active_rule(self):
        """When a renamed rule creates a second DB record (same logical rule,
        different id), deactivating the old rule and having active_test=False
        leak must not create a duplicate via the old rule.

        This reproduces the exact A1 bug scenario: rule 9 (old, inactive) and
        rule 46 (new, active) both match, but the dedup key (rule_id, res_id)
        only catches rule 46's match because service was created by rule 46."""
        AutoAdd = self.env["riverflow.auto.add.service"]
        subjects = self.subject_partner

        # Create a second rule pointing to the same domain (simulates the XML ID rename)
        new_rule = self.env["riverflow.auto.add.service"].create(
            {
                "domain_id": self.auto_add_domain.id,
                "service_template_id": self.service_template.id,
            }
        )

        # Let the new rule create the initial service
        AutoAdd.auto_add_services(subjects)
        # Both rules matched, two services created (one per rule)
        self.assertEqual(self._count_services_for_subject(), 2)

        # Delete one of the two services and deactivate old rule
        # (simulates the consolidation: reassign service, deactivate old rule)
        old_rule_service = self.env["riverflow.service"].search(
            [
                ("res_id", "=", self.subject_partner.id),
                ("res_model", "=", "res.partner"),
                ("created_by_auto_add_service_id", "=", self.auto_add_rule.id),
            ]
        )
        old_rule_service.unlink()
        self.auto_add_rule.active = False
        self.assertEqual(self._count_services_for_subject(), 1)

        # Now simulate the context leak
        AutoAdd.with_context(active_test=False).auto_add_services(subjects)

        self.assertEqual(
            self._count_services_for_subject(),
            1,
            "Deactivated old rule must not create a service even when "
            "active_test=False is in context and a newer active rule exists",
        )
