from odoo import models, _
from odoo.exceptions import UserError

import json


class RiverflowTransitionMixin(models.AbstractModel):
    _name = "riverflow.transition.mixin"
    _description = "Base class with function to create an action to open a transition action wizard"

    def _prepare_transition_action(self):
        transition_id = self.env.context.get("transition_id")
        transition = self.env["riverflow.transition"].browse(transition_id)
        if not transition:
            raise UserError(_("No transition selected."))

        action_context = {}
        if transition.action_context:
            try:
                action_context = json.loads(transition.action_context) or {}
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Bad action_context '{transition.action_context}', for transition '{transition.name}': {str(e)}",
                    transition.action_context,
                    e.pos,
                ) from e

        action_context["transition_id"] = transition.id

        defaults_context = {}
        isWizard = self._transient
        if isWizard:
            # start transition selection wizard; carry over the default field values passed in by the caller
            for key, value in self.env.context.items():
                if key.startswith("default_"):
                    defaults_context[key] = value
        elif len(self.ids) == 1:
            # Actual entity, such as a Service. We copy the record's fields to defaults for the transition action wizard
            for field_name in self._fields:
                field = self._fields[field_name]
                value = getattr(self, field_name)
                converted_value = field.convert_to_cache(value, self)
                defaults_context["default_" + field_name] = converted_value

        action_context.update(defaults_context)

        view = self.env.ref(transition.action_id.odoo_view)
        res_model = view.model

        action = {
            "type": "ir.actions.act_window",
            "name": f"{transition.name}",
            "res_model": res_model,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": action_context,
        }

        return action
