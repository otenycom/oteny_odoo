from odoo import models, api
import json


class RiverflowWorkflowTransitionMixin(models.AbstractModel):
    _name = "riverflow.workflow.transition.mixin"
    _description = "Mixin to support workflow transitions"

    def _prepare_transition_action(self, transition):
        action_context = {}
        if transition.action_context:
            try:
                action_context = json.loads(transition.action_context) or {}
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Bad action_context '{transition.action_context}', for transition '{transition.name}': {str(e)}", # fmt: off
                    transition.action_context,
                    e.pos
                ) from e

        action_context['transition_id'] = transition.id

        isWizard = self._transient
        if not isWizard and len(self.ids) == 1:
            # Actual entity, we copy the record fields to defaults for the transition action wizard
            defaults_context = {}
            for field_name in self._fields:
                field = self._fields[field_name]
                value = getattr(self, field_name)
                converted_value = field.convert_to_cache(value, self)
                defaults_context['default_' + field_name] = converted_value

            action_context.update(defaults_context)

        view = self.env.ref(transition.action_id.odoo_view)
        res_model = view.model

        action = {
            'type': 'ir.actions.act_window',
            'name': f'{transition.name}',
            'res_model': res_model,
            'view_mode': 'form',
            'views': [(view.id, "form")],
            'target': 'new',
            'context': action_context,
        }

        return action
