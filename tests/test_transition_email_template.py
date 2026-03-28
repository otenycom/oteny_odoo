from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install", "riverflow", "test_transition_email_template")
class TestTransitionEmailTemplate(TransactionCase):
    """Test mail_template_id on riverflow.transition and fallback logic
    in the email sender wizard.

    The transition-level template allows different email transitions within
    the same workflow to use different templates (e.g., AB appointment request
    vs. pickup request in the Work Permit workflow).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        Service = cls.env["riverflow.service"]
        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        cls.email_action = cls.env.ref("riverflow.transition_action_email_sender")

        cls.workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "Test Email Template WF",
        })
        cls.state_a = State.create({
            "workflow_id": cls.workflow.id,
            "name": "State A",
            "sequence": 10,
        })
        cls.state_b = State.create({
            "workflow_id": cls.workflow.id,
            "name": "State B",
            "sequence": 20,
        })

        # Two email templates for testing
        cls.template_alpha = cls.env["mail.template"].create({
            "name": "Template Alpha",
            "model_id": service_model.id,
            "subject": "Alpha subject",
            "body_html": "<p>Alpha body</p>",
        })
        cls.template_beta = cls.env["mail.template"].create({
            "name": "Template Beta",
            "model_id": service_model.id,
            "subject": "Beta subject",
            "body_html": "<p>Beta body</p>",
        })

        # Transition with template set
        cls.trans_with_template = Transition.create({
            "name": "Send Alpha",
            "from_state_id": cls.state_a.id,
            "to_state_id": cls.state_b.id,
            "action_id": cls.email_action.id,
            "mail_template_id": cls.template_alpha.id,
            "sequence": 10,
        })

        # Transition without template (should fall back to service)
        cls.trans_without_template = Transition.create({
            "name": "Send Fallback",
            "from_state_id": cls.state_a.id,
            "to_state_id": cls.state_b.id,
            "action_id": cls.email_action.id,
            "sequence": 20,
        })

        # Service with its own template
        cls.service = Service.create({
            "name": "Test Service",
            "state_id": cls.state_a.id,
            "company_id": cls.env.company.id,
            "mail_template_id": cls.template_beta.id,
        })

    def test_transition_mail_template_id_field(self):
        """The mail_template_id field exists on riverflow.transition."""
        self.assertIn("mail_template_id", self.env["riverflow.transition"]._fields)
        self.assertEqual(self.trans_with_template.mail_template_id, self.template_alpha)
        self.assertFalse(self.trans_without_template.mail_template_id)

    def _wizard_defaults(self, transition, service):
        """Open the email sender wizard as if the transition button was clicked."""
        Wizard = self.env["riverflow.service.email.sender.wizard"]
        return Wizard.with_context(
            transition_id=transition.id,
            active_model="riverflow.service",
            active_ids=service.ids,
        ).default_get(Wizard._fields.keys())

    def test_email_wizard_prefers_transition_template(self):
        """When the transition has a mail_template_id, the wizard uses it
        instead of the service's template."""
        defaults = self._wizard_defaults(self.trans_with_template, self.service)

        self.assertEqual(
            defaults.get("mail_template_id"),
            self.template_alpha.id,
            "Wizard should use the transition's template (Alpha), not the service's (Beta)",
        )

    def test_email_wizard_falls_back_to_service_template(self):
        """When the transition has no mail_template_id, the wizard falls
        back to the service's mail_template_id."""
        defaults = self._wizard_defaults(self.trans_without_template, self.service)

        self.assertEqual(
            defaults.get("mail_template_id"),
            self.template_beta.id,
            "Wizard should fall back to the service's template (Beta)",
        )

    def test_email_wizard_no_template_anywhere(self):
        """When neither transition nor service has a template, wizard
        should not set mail_template_id."""
        service_no_tpl = self.env["riverflow.service"].create({
            "name": "No Template Service",
            "state_id": self.state_a.id,
            "company_id": self.env.company.id,
        })
        defaults = self._wizard_defaults(self.trans_without_template, service_no_tpl)

        self.assertFalse(
            defaults.get("mail_template_id"),
            "Wizard should not set mail_template_id when neither transition nor service has one",
        )
