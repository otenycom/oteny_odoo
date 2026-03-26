from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_deferred_children")
class TestDeferredChildrenContextIsolation(TransactionCase):
    """Test that deferred children don't inherit parent field values via context.

    The transition mixin copies ALL parent fields as default_* context keys
    for wizard form pre-population. _create_deferred_children must isolate
    child creation from these leaked defaults — children should get values
    from the template only, not from the parent service.

    supply_unit_price is used as the test proxy: it's a stored field on
    riverflow.service that _create_service_member_from_template does NOT
    explicitly set in its vals dict, making it vulnerable to context leaks.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        Service = cls.env["riverflow.service"]
        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")

        cls.workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Deferred WF",
        })
        cls.state_initial = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Initial",
            "sequence": 10,
        })
        cls.state_booked = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Booked",
            "sequence": 20,
        })

        cls.child_workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Child WF",
        })
        cls.child_state = State.create({
            "workflow_id": cls.child_workflow.id,
            "name": "Not Started",
            "sequence": 10,
        })

        cls.trans_book = Transition.create({
            "name": "Book",
            "workflow_id": cls.workflow.id,
            "from_state_id": cls.state_initial.id,
            "to_state_id": cls.state_booked.id,
            "action_id": default_action.id,
            "sequence": 10,
        })

        # Template with a deferred child
        cls.template = Service.create({
            "name": "Test Parent Template",
            "workflow_id": cls.workflow.id,
            "state_id": cls.state_initial.id,
            "is_this_a_template": True,
            "company_id": cls.env.company.id,
        })
        cls.child_template = Service.create({
            "name": "Deferred Child Template",
            "parent_id": cls.template.id,
            "workflow_id": cls.child_workflow.id,
            "state_id": cls.child_state.id,
            "create_on_state_id": cls.state_booked.id,
            "company_id": cls.env.company.id,
        })

        # Use res.partner as the generic subject
        cls.subject = cls.env.company.partner_id

    def _create_service_from_template(self):
        """Clone the template into a service instance linked to a subject."""
        service = self.env["riverflow.service"].with_context(
            default_res_model="res.partner",
            default_res_id=self.subject.id,
        )._create_services_from_template(self.template.id)
        return service

    def _fire_transition(self, service, transition):
        """Execute a transition through the full mixin flow.

        Calls _prepare_transition_action on the service to get the action
        context (which copies ALL service fields as default_* keys), then
        creates and executes the wizard in that context. This reproduces
        the real-world flow where the mixin's defaults leak into action_save.
        """
        action = service.with_context(
            transition_id=transition.id,
        )._prepare_transition_action()

        wizard_ctx = action["context"]
        wizard_ctx["active_model"] = "riverflow.service"
        wizard_ctx["active_ids"] = service.ids

        Wizard = self.env[action["res_model"]].with_context(**wizard_ctx)
        defaults = Wizard.default_get(Wizard.fields_get().keys())
        wizard = Wizard.create(defaults)
        wizard.action_save()

    def test_deferred_child_does_not_inherit_parent_supply_unit_price(self):
        """Context default for supply_unit_price must not leak to deferred children.

        The parent service has supply_unit_price=999. The transition mixin
        copies this as default_supply_unit_price=999 into context. The
        deferred child template has supply_unit_price=0 (the default).
        Without context isolation, the child would inherit 999 from context.
        """
        service = self._create_service_from_template()
        self.assertFalse(service.child_ids, "Deferred children skipped on initial clone")

        # Set a distinctive value on the parent — the mixin will copy it as
        # default_supply_unit_price into context when opening the wizard.
        service.supply_unit_price = 999.0

        self._fire_transition(service, self.trans_book)

        children = service.child_ids.filtered("active")
        self.assertEqual(len(children), 1, "Deferred child should be created")
        self.assertEqual(
            children[0].supply_unit_price,
            0.0,
            "Deferred child must get supply_unit_price from template (0), "
            "not from parent's leaked context default (999)",
        )

    def test_deferred_child_gets_correct_subject_link(self):
        """Deferred children must be linked to the same subject as the parent."""
        service = self._create_service_from_template()
        self._fire_transition(service, self.trans_book)

        children = service.child_ids.filtered("active")
        self.assertEqual(len(children), 1)
        self.assertEqual(
            children[0].res_model,
            "res.partner",
            "Deferred child should inherit res_model from parent",
        )
        self.assertEqual(
            children[0].res_id,
            self.subject.id,
            "Deferred child should inherit res_id from parent",
        )
