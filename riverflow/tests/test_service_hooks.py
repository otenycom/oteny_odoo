"""riverflow names no app model: a state change and an email render reach the app
through two hooks, each empty here."""
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_service_hooks")
class TestServiceHooks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Service = cls.env["riverflow.service"]
        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        cls.workflow = Workflow.create({"model_id": service_model.id, "name": "Hook WF"})
        cls.state_a = State.create({"workflow_id": cls.workflow.id, "name": "A", "sequence": 10})
        cls.state_b = State.create({"workflow_id": cls.workflow.id, "name": "B", "sequence": 20})
        cls.service = Service.create({
            "name": "Hooked service",
            "workflow_id": cls.workflow.id,
            "state_id": cls.state_a.id,
        })

    def test_state_write_calls_the_hook_once_per_write(self):
        Service = type(self.service)
        with patch.object(Service, "_on_state_changed", autospec=True) as hook:
            self.service.write({"state_id": self.state_b.id})
            self.assertEqual(hook.call_count, 1)
            self.assertEqual(hook.call_args.args[0], self.service)
            self.service.write({"name": "renamed"})
            self.assertEqual(hook.call_count, 1, "a write without state_id does not call the hook")

    def test_render_context_carries_no_app_model_by_default(self):
        # riverflow's own hook is empty; an installed app may extend it, so the
        # assertion targets riverflow's function, not the merged model's.
        from odoo.addons.riverflow.wizards import riverflow_service_email_sender as mod
        wizard = self.env["riverflow.service.email.sender.wizard"]
        base = mod.RiverflowServiceEmailSenderWizard._render_context_extra
        self.assertEqual(base(wizard, self.service, 0), {})
        ctx = wizard._get_render_context(self.service, {})
        self.assertLessEqual({"service", "company"}, set(ctx))
