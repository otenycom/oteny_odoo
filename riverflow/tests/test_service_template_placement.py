from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_template_placement")
class TestServiceTemplatePlacement(TransactionCase):
    """Test placement guard rails for service templates.

    Placement rules (can_be_root_service, can_be_child_service,
    allowed_subject_model_ids) control which templates can be
    instantiated in which context — preventing users from creating
    log-entry-only services on employees/ships, or adding root-only
    templates as children.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.user_model = cls.env["ir.model"]._get("res.users")

        # Subject record used for testing
        cls.subject_partner = cls.env["res.partner"].create({"name": "Test Subject"})

        # Unrestricted template (all defaults)
        cls.template_unrestricted = cls.env["riverflow.service"].create(
            {
                "name": "Unrestricted Template",
                "is_this_a_template": True,
            }
        )

        # Template restricted to res.partner only
        cls.template_partner_only = cls.env["riverflow.service"].create(
            {
                "name": "Partner Only Template",
                "is_this_a_template": True,
                "allowed_subject_model_ids": [(4, cls.partner_model.id)],
            }
        )

        # Template that cannot be a root service (child-only)
        cls.template_child_only = cls.env["riverflow.service"].create(
            {
                "name": "Child Only Template",
                "is_this_a_template": True,
                "can_be_root_service": False,
            }
        )

        # Template that cannot be a child service (root-only)
        cls.template_root_only = cls.env["riverflow.service"].create(
            {
                "name": "Root Only Template",
                "is_this_a_template": True,
                "can_be_child_service": False,
            }
        )

    # -- Subject model restriction tests --

    def test_allowed_subject_blocks_wrong_model(self):
        """Template restricted to res.partner rejects res.users subject."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.users",
            default_res_id=self.env.user.id,
        )
        with self.assertRaises(UserError):
            Service._create_service_member_from_template(self.template_partner_only)

    def test_allowed_subject_accepts_correct_model(self):
        """Template restricted to res.partner accepts res.partner subject."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        )
        new_service = Service._create_service_member_from_template(self.template_partner_only)
        self.assertTrue(new_service)
        self.assertEqual(new_service.res_model, "res.partner")

    def test_empty_allowed_subjects_accepts_any_model(self):
        """Template with no allowed_subject_model_ids accepts any subject."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.users",
            default_res_id=self.env.user.id,
        )
        new_service = Service._create_service_member_from_template(self.template_unrestricted)
        self.assertTrue(new_service)

    # -- Root / child flag tests --

    def test_child_only_template_blocks_root_creation(self):
        """Template with can_be_root_service=False cannot be created as root."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        )
        with self.assertRaises(UserError):
            Service._create_service_member_from_template(self.template_child_only)

    def test_child_only_template_accepts_child_creation(self):
        """Template with can_be_root_service=False can be created as child."""
        # First create a parent service
        parent = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        ).create({"name": "Parent Service"})

        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        )
        new_service = Service._create_service_member_from_template(
            self.template_child_only, parent_id=parent.id
        )
        self.assertTrue(new_service)
        self.assertEqual(new_service.parent_id.id, parent.id)

    def test_root_only_template_blocks_child_creation(self):
        """Template with can_be_child_service=False cannot be created as child."""
        parent = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        ).create({"name": "Parent Service"})

        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        )
        with self.assertRaises(UserError):
            Service._create_service_member_from_template(
                self.template_root_only, parent_id=parent.id
            )

    def test_root_only_template_accepts_root_creation(self):
        """Template with can_be_child_service=False can be created as root."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        )
        new_service = Service._create_service_member_from_template(self.template_root_only)
        self.assertTrue(new_service)
        self.assertFalse(new_service.parent_id)

    # -- No-subject tests --

    def test_restricted_template_blocks_no_subject(self):
        """Template with allowed_subject_model_ids rejects creation without a subject."""
        Service = self.env["riverflow.service"]
        with self.assertRaises(UserError):
            Service._create_service_member_from_template(self.template_partner_only)

    def test_unrestricted_template_allows_no_subject(self):
        """Template without allowed_subject_model_ids allows creation without a subject."""
        Service = self.env["riverflow.service"]
        new_service = Service._create_service_member_from_template(self.template_unrestricted)
        self.assertTrue(new_service)

    # -- Bypass context test --

    def test_skip_context_bypasses_placement_check(self):
        """Context flag skip_service_template_placement_check disables validation."""
        Service = self.env["riverflow.service"].with_context(
            default_res_model="res.users",
            default_res_id=self.env.user.id,
            skip_service_template_placement_check=True,
        )
        new_service = Service._create_service_member_from_template(self.template_partner_only)
        self.assertTrue(new_service)

    # -- Helper method tests --

    def test_placement_allowed_helper_returns_bool(self):
        """_template_placement_allowed returns correct bool for various scenarios."""
        Service = self.env["riverflow.service"]

        # Correct model, root add
        self.assertTrue(
            Service._template_placement_allowed(
                self.template_partner_only, res_model="res.partner", is_child_add=False
            )
        )
        # Wrong model
        self.assertFalse(
            Service._template_placement_allowed(
                self.template_partner_only, res_model="res.users", is_child_add=False
            )
        )
        # Child-only as root
        self.assertFalse(
            Service._template_placement_allowed(
                self.template_child_only, res_model="res.partner", is_child_add=False
            )
        )
        # Root-only as child
        self.assertFalse(
            Service._template_placement_allowed(
                self.template_root_only, res_model="res.partner", is_child_add=True
            )
        )
        # Restricted template with no subject
        self.assertFalse(
            Service._template_placement_allowed(
                self.template_partner_only, res_model=None, is_child_add=False
            )
        )
        # Unrestricted template with no subject
        self.assertTrue(
            Service._template_placement_allowed(
                self.template_unrestricted, res_model=None, is_child_add=False
            )
        )


@tagged("post_install", "-at_install", "riverflow", "test_template_placement")
class TestWizardTemplateFiltering(TransactionCase):
    """Test that the Add Service wizard filters templates by placement rules."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.subject_partner = cls.env["res.partner"].create({"name": "Wizard Test Subject"})

        # Template restricted to res.partner
        cls.template_for_partner = cls.env["riverflow.service"].create(
            {
                "name": "For Partner",
                "is_this_a_template": True,
                "allowed_subject_model_ids": [(4, cls.partner_model.id)],
            }
        )

        # Template restricted to res.users (should not appear for partner)
        cls.user_model = cls.env["ir.model"]._get("res.users")
        cls.template_for_user = cls.env["riverflow.service"].create(
            {
                "name": "For User Only",
                "is_this_a_template": True,
                "allowed_subject_model_ids": [(4, cls.user_model.id)],
            }
        )

    def test_wizard_excludes_templates_for_wrong_subject(self):
        """Wizard JSON should not include templates whose allowed_subject_model_ids
        excludes the current subject model."""
        wizard = self.env["riverflow.start.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject_partner.id,
        ).create({})
        buttons_json = wizard.transition_buttons_json
        template_names = [
            b["caption"].strip()
            for b in buttons_json.get("buttons", [])
            if b.get("is_template")
        ]
        self.assertIn("For Partner", template_names)
        self.assertNotIn("For User Only", template_names)
