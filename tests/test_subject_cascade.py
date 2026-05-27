from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_subject_cascade")
class SubjectCascadeTestCase(TransactionCase):
    """Cascade of res_model/res_id through the service tree.

    The cascade is keyed off subject_from. Default 'inherit' pulls from the
    immediate parent; 'self' keeps the service's own subject. Higher-layer
    modules can add custom modes via selection_add + _apply_custom_subject_from.
    """

    TEST_PREFIX = "TestRunSubject "

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a = cls.env["res.partner"].create({"name": f"{cls.TEST_PREFIX}A"})
        cls.partner_b = cls.env["res.partner"].create({"name": f"{cls.TEST_PREFIX}B"})

    def _cleanup(self):
        self.env["riverflow.service"].search([("name", "like", f"{self.TEST_PREFIX}%")]).unlink()

    def test_default_inherit_cascades_from_parent_through_tree(self):
        # Single-subject chain: root has partner A, children/grandchildren
        # inherit partner A via subject_from='inherit' (the default for
        # records with a parent_id). Roots default to subject_from='self'
        # so the cascade never clobbers their own subject.
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        child = self.env["riverflow.service"].create(
            {"name": f"{self.TEST_PREFIX}child", "parent_id": root.id}
        )
        grand = self.env["riverflow.service"].create(
            {"name": f"{self.TEST_PREFIX}grand", "parent_id": child.id}
        )
        self.assertEqual(root.subject_from, "self")
        self.assertEqual(child.subject_from, "inherit")
        self.assertEqual(child.res_model, "res.partner")
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(grand.res_model, "res.partner")
        self.assertEqual(grand.res_id, self.partner_a.id)

    def test_self_breaks_cascade_descendants_inherit_from_breaker(self):
        # The middle service uses subject_from='self' with partner B; the
        # grandchild defaults to 'inherit' so it pulls from the middle service
        # (partner B), NOT from the root (partner A).
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        middle = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}middle",
                "parent_id": root.id,
                "subject_from": "self",
                "res_model": "res.partner",
                "res_id": self.partner_b.id,
            }
        )
        grand = self.env["riverflow.service"].create(
            {"name": f"{self.TEST_PREFIX}grand", "parent_id": middle.id}
        )
        # Middle keeps its own subject (partner B).
        self.assertEqual(middle.res_model, "res.partner")
        self.assertEqual(middle.res_id, self.partner_b.id)
        # Grandchild cascades from parent (middle = B), not root (A).
        self.assertEqual(grand.res_model, "res.partner")
        self.assertEqual(grand.res_id, self.partner_b.id)

    def test_root_subject_change_recomputes_inheriting_descendants_only(self):
        # When the root's subject changes, only descendants whose path back
        # to the root is fully 'inherit' should recompute. The 'self' middle
        # holds the line.
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        inheriting_child = self.env["riverflow.service"].create(
            {"name": f"{self.TEST_PREFIX}inheriting", "parent_id": root.id}
        )
        self_child = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}self_child",
                "parent_id": root.id,
                "subject_from": "self",
                "res_model": "res.partner",
                "res_id": self.partner_b.id,
            }
        )
        new_partner = self.env["res.partner"].create({"name": f"{self.TEST_PREFIX}C"})
        root.res_id = new_partner.id
        self.assertEqual(inheriting_child.res_id, new_partner.id)
        self.assertEqual(self_child.res_id, self.partner_b.id)

    def test_root_defaults_to_self(self):
        # A service created without parent_id (a root) gets subject_from='self'
        # by default. Its res_id sticks across writes because the compute's
        # 'self' branch leaves the value alone.
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        self.assertEqual(root.subject_from, "self")
        self.assertEqual(root.res_id, self.partner_a.id)
        # Direct write is allowed (readonly=False); the 'self' compute branch
        # then leaves it alone on recompute -- the new value sticks.
        root.res_id = self.partner_b.id
        self.assertEqual(root.res_id, self.partner_b.id)

    def test_explicit_inherit_on_root_is_noop(self):
        # Even if someone explicitly creates a root with subject_from='inherit'
        # (bypassing the create() default), the compute's parent_id guard in
        # the inherit branch protects the root from being clobbered to
        # (False, 0).
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
                "subject_from": "inherit",
            }
        )
        self.assertEqual(root.subject_from, "inherit")
        self.assertEqual(root.res_model, "res.partner")
        self.assertEqual(root.res_id, self.partner_a.id)

    def test_orphaning_preserves_subject(self):
        # Clearing parent_id on a child should NOT clobber its subject to
        # (False, 0). The compute's parent_id guard in the inherit branch
        # handles this: with no parent, the inherit branch is a no-op and
        # res_id / res_model retain their last value.
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        child = self.env["riverflow.service"].create(
            {"name": f"{self.TEST_PREFIX}child", "parent_id": root.id}
        )
        # Pre-condition: child inherited partner A from root.
        self.assertEqual(child.subject_from, "inherit")
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(child.res_model, "res.partner")
        # Orphan the child by clearing parent_id.
        child.parent_id = False
        # Subject must be preserved, not cleared.
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(child.res_model, "res.partner")

    def test_template_clone_copies_subject_from(self):
        # _get_template_clone_vals must propagate subject_from to cloned
        # instances. A template marked 'self' must produce instances also
        # marked 'self'.
        self._cleanup()
        workflow = self.env["riverflow.workflow"].create(
            {
                "name": f"{self.TEST_PREFIX}wf",
                "model_id": self.env.ref("riverflow.model_riverflow_service").id,
            }
        )
        initial_state = self.env["riverflow.state"].create(
            {"name": "Not Started", "workflow_id": workflow.id, "sequence": 10}
        )
        # Bootstrap transition (from no state)
        self.env["riverflow.transition"].create(
            {
                "name": "Start",
                "workflow_id": workflow.id,
                "to_state_id": initial_state.id,
                "action_id": self.env.ref("riverflow.transition_action_default").id,
                "sequence": 10,
            }
        )
        template = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}template",
                "workflow_id": workflow.id,
                "state_id": initial_state.id,
                "is_this_a_template": True,
                "subject_from": "self",
            }
        )
        instance = self.env["riverflow.service"]._create_service_member_from_template(
            template
        )
        self.assertEqual(instance.subject_from, "self")
