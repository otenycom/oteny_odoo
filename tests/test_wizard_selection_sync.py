from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "riverflow", "test_wizard_selection_sync")
class TestWizardSelectionSync(TransactionCase):
    """The service wizard must accept every use_project_deadline_from value
    that the service model can store.

    When a user opens a transition wizard on an existing service, the
    _prepare_transition_action mixin copies field values as default_* context
    keys. If the wizard's Selection field doesn't include the service's current
    value, Odoo raises a ValueError during onchange / cache validation.

    Regression: root_appointment and creation were missing from the wizard
    Selection, causing a server error for ~160 production services.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        State = cls.env["riverflow.state"]
        Workflow = cls.env["riverflow.workflow"]
        Transition = cls.env["riverflow.transition"]
        service_model = cls.env["ir.model"]._get("riverflow.service")
        default_action = cls.env.ref("riverflow.transition_action_default")

        cls.workflow = Workflow.create({
            "model_id": service_model.id,
            "name": "WizSelSync WF",
        })
        cls.state_new = State.create({
            "workflow_id": cls.workflow.id,
            "name": "New",
            "sequence": 10,
        })
        cls.state_done = State.create({
            "workflow_id": cls.workflow.id,
            "name": "Done",
            "sequence": 20,
            "is_end_state": True,
        })
        cls.transition = Transition.create({
            "name": "Finish",
            "from_state_id": cls.state_new.id,
            "to_state_id": cls.state_done.id,
            "action_id": default_action.id,
            "sequence": 10,
        })

        cls.root = cls.env["riverflow.service"].create({
            "name": "WizSelSync Root",
            "project_deadline": date(2026, 6, 15),
            "supply_actual_date": date(2026, 7, 20),
        })

    def _open_wizard_via_mixin(self, service):
        """Reproduce the real-world flow: _prepare_transition_action copies
        every shared field from the service into default_* context keys, then
        the wizard is created from those defaults."""
        action = service.with_context(
            transition_id=self.transition.id,
        )._prepare_transition_action()

        wizard_ctx = action["context"]
        wizard_ctx["active_model"] = "riverflow.service"
        wizard_ctx["active_ids"] = service.ids

        Wizard = self.env[action["res_model"]].with_context(**wizard_ctx)
        defaults = Wizard.default_get(Wizard.fields_get().keys())
        wizard = Wizard.create(defaults)
        return wizard

    def test_wizard_accepts_root_appointment(self):
        """Opening the wizard on a service with root_appointment must not raise."""
        child = self.env["riverflow.service"].create({
            "name": "WizSelSync Child RA",
            "parent_id": self.root.id,
            "use_project_deadline_from": "root_appointment",
            "days_relative_to_project": 0,
            "workflow_id": self.workflow.id,
            "state_id": self.state_new.id,
        })
        wizard = self._open_wizard_via_mixin(child)
        self.assertEqual(wizard.use_project_deadline_from, "root_appointment")

    def test_wizard_accepts_creation(self):
        """Opening the wizard on a service with creation must not raise."""
        child = self.env["riverflow.service"].create({
            "name": "WizSelSync Child Cr",
            "parent_id": self.root.id,
            "use_project_deadline_from": "creation",
            "days_relative_to_project": 0,
            "workflow_id": self.workflow.id,
            "state_id": self.state_new.id,
        })
        wizard = self._open_wizard_via_mixin(child)
        self.assertEqual(wizard.use_project_deadline_from, "creation")

    def test_wizard_selection_is_superset_of_service(self):
        """Every selection key on riverflow.service must also be valid on the wizard."""
        service_field = self.env["riverflow.service"]._fields["use_project_deadline_from"]
        wizard_field = self.env["riverflow.service.wizard"]._fields["use_project_deadline_from"]

        service_keys = {k for k, _v in service_field._description_selection(self.env)}
        wizard_keys = {k for k, _v in wizard_field._description_selection(self.env)}

        missing = service_keys - wizard_keys
        self.assertFalse(
            missing,
            f"Wizard selection is missing keys from service: {missing}",
        )
