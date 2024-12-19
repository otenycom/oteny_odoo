from odoo import models, _
from odoo.exceptions import UserError
import ast


class RiverflowTransitionMixin(models.AbstractModel):
    _name = "riverflow.transition.mixin"
    _description = "Base class with function to create an action to open a transition action wizard"

    def _prepare_transition_action(self):
        transition_id = self.env.context.get("transition_id")
        transition = self.env["riverflow.transition"].browse(transition_id)
        if not transition:
            raise UserError(_("No transition selected."))

        isWizard = self._transient
        if not isWizard:  # start transition selection wizard has no state_id
            current_state = self.state_id
            expected_state = transition.from_state_id

            if expected_state and current_state != expected_state:
                raise UserError(
                    _(
                        "Another user just updated this record. Please refresh and try again."
                    )
                )

        action_context = self._prepare_action_context(transition)
        action_context["transition_id"] = transition.id

        defaults_context = {}
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

        odoo_view = transition.action_id.odoo_view
        if "." not in odoo_view:
            odoo_view = f"riverflow.{odoo_view}"
        view = self.sudo().env.ref(odoo_view)
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

    def _prepare_action_context(self, transition):
        action_context = {}
        if transition.action_context:
            try:
                action_context = ast.literal_eval(transition.action_context) or {}
            except (ValueError, SyntaxError) as e:
                raise UserError(
                    _(
                        f"Bad action_context '{transition.action_context}', for transition '{transition.name}': {str(e)}"
                    )
                ) from e
            action_context = self._process_references(transition, action_context)
        return action_context

    def _process_references(self, transition, action_context):
        updated_context = {}
        for key, value in action_context.items():
            if key.endswith("_id_ref"):
                full_xml_id = value
                transition_xml_id = transition.get_external_id().get(transition.id, "")
                if not transition_xml_id:
                    raise UserError(
                        _(f"No external ID found for transition '{transition.name}'")
                    )
                if "." not in value and "." in transition_xml_id:
                    module_name = transition_xml_id.split(".")[0]
                    full_xml_id = f"{module_name}.{value}"

                try:
                    referenced_record = self.env.ref(full_xml_id)
                    referenced_id = referenced_record.id
                except ValueError as e:
                    raise UserError(
                        _(
                            f"Invalid XML ID '{full_xml_id}' for field '{key}' in transition '{transition.name}': {str(e)}"
                        )
                    ) from e

                new_key = key[:-4]  # strip the trailing '_ref' from the key name
                updated_context[new_key] = referenced_id
            else:
                updated_context[key] = value

        return updated_context
