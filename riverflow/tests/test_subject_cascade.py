from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_subject_cascade")
class SubjectCascadeTestCase(TransactionCase):
    """Cascade of res_model/res_id through the service tree.

    The cascade is keyed off subject_from. The single base mode 'default' is
    parent-aware: a service with a parent pulls the parent's subject, while a
    service with no parent keeps the subject it was created with. Higher-layer
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

    def test_default_cascades_from_parent_through_tree(self):
        # Single-subject chain: root has partner A, children/grandchildren
        # inherit partner A via subject_from='default' (the field default).
        # The root, having no parent, keeps its own subject under 'default'.
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
        self.assertEqual(root.subject_from, "default")
        self.assertEqual(child.subject_from, "default")
        self.assertEqual(child.res_model, "res.partner")
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(grand.res_model, "res.partner")
        self.assertEqual(grand.res_id, self.partner_a.id)

    def test_root_subject_change_cascades_to_descendants(self):
        # When the root's subject changes, all 'default' descendants recompute
        # and follow the new subject.
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
        # Pre-condition: whole chain on partner A.
        self.assertEqual(grand.res_id, self.partner_a.id)
        # Change the root subject; the chain follows.
        root.res_id = self.partner_b.id
        self.assertEqual(child.res_id, self.partner_b.id)
        self.assertEqual(grand.res_id, self.partner_b.id)

    def test_root_keeps_own_subject_under_default(self):
        # A service created without parent_id (a root) gets subject_from='default'
        # by default. Its res_id sticks across writes because the compute's
        # parent_id guard leaves a parentless service alone.
        self._cleanup()
        root = self.env["riverflow.service"].create(
            {
                "name": f"{self.TEST_PREFIX}root",
                "res_model": "res.partner",
                "res_id": self.partner_a.id,
            }
        )
        self.assertEqual(root.subject_from, "default")
        self.assertEqual(root.res_id, self.partner_a.id)
        # Direct write is allowed (readonly=False); the parent_id guard then
        # leaves it alone on recompute -- the new value sticks.
        root.res_id = self.partner_b.id
        self.assertEqual(root.res_id, self.partner_b.id)

    def test_orphaning_preserves_subject(self):
        # Clearing parent_id on a child should NOT clobber its subject to
        # (False, 0). The compute's parent_id guard handles this: with no
        # parent, the default branch is a no-op and res_id / res_model retain
        # their last value.
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
        self.assertEqual(child.subject_from, "default")
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(child.res_model, "res.partner")
        # Orphan the child by clearing parent_id.
        child.parent_id = False
        # Subject must be preserved, not cleared.
        self.assertEqual(child.res_id, self.partner_a.id)
        self.assertEqual(child.res_model, "res.partner")

    def test_template_clone_copies_subject_from(self):
        # _get_template_clone_vals must propagate subject_from to cloned
        # instances. A template marked 'default' must produce instances also
        # marked 'default'.
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
                "subject_from": "default",
            }
        )
        instance = self.env["riverflow.service"]._create_service_member_from_template(
            template
        )
        self.assertEqual(instance.subject_from, "default")
