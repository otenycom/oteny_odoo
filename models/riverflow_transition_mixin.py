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

            # #region agent log
            import json as _json, time as _time
            with open("/Users/thijsvanwaaij/oteny/radar/.cursor/debug-2eb149.log", "a") as _f:
                _f.write(_json.dumps({"sessionId": "2eb149", "hypothesisId": "H1", "location": "riverflow_transition_mixin.py:_prepare_transition_action", "message": "state check in _prepare_transition_action", "data": {"record_model": self._name, "record_id": self.id, "current_state": current_state.name if current_state else None, "current_state_id": current_state.id if current_state else None, "expected_state": expected_state.name if expected_state else None, "expected_state_id": expected_state.id if expected_state else None, "transition_name": transition.name, "transition_id": transition.id, "match": bool(not expected_state or current_state == expected_state)}, "timestamp": int(_time.time() * 1000)}) + "\n")
            # #endregion

            if expected_state and current_state != expected_state:
                raise UserError(_("Another user just updated this record. Please refresh and try again."))

        action_context = self._prepare_action_context(transition)
        action_context["transition_id"] = transition.id

        # Resolve the wizard model before building defaults, so we can
        # filter to only fields the wizard declares.
        odoo_view = transition.action_id.odoo_view
        if "." not in odoo_view:
            odoo_view = f"riverflow.{odoo_view}"
        view = self.sudo().env.ref(odoo_view)
        res_model = view.model

        defaults_context = {}
        if isWizard:
            # start transition selection wizard; carry over the default field values passed in by the caller
            for key, value in self.env.context.items():
                if key.startswith("default_"):
                    defaults_context[key] = value
        elif len(self.ids) == 1:
            # Pre-populate the wizard with current entity field values.
            # Access ALL entity fields (getattr triggers stored computes that
            # must fire for state_record tracker consistency), but only include
            # fields the wizard model declares in the context defaults. Entity-
            # only fields (is_service_with_journey, credential_ids, supply_unit_price,
            # etc.) must not leak into context where they pollute create() calls
            # on unrelated models during action_save.
            wizard_fields = set(self.env[res_model]._fields.keys())
            for field_name in self._fields:
                field = self._fields[field_name]
                value = getattr(self, field_name)
                converted_value = field.convert_to_cache(value, self)
                if field_name in wizard_fields:
                    defaults_context["default_" + field_name] = converted_value

        action_context.update(defaults_context)

        title = transition.name if not transition.from_state_id else f"{transition.workflow_name} | {transition.name}"
        action = {
            "type": "ir.actions.act_window",
            "name": title,
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
                    raise UserError(_(f"No external ID found for transition '{transition.name}'"))
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
