/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TransitionButtons extends Component {
    // Consider refactoring this class similar to hr_expense.ListButtons
    // or wrap the buttons in a popover, to fit an unlimited number of buttons
    static template = "riverflow.TransitionButtons";
    static props = {
        ...standardFieldProps,
        buttons: { type: Object, optional: true },
    };

    setup() {
        // returns 'transition_buttons_json' field value
        function fieldValue(props) {
            const jsonValue = props.record.data[props.name];

            if (!jsonValue) {
                return {
                    buttons: [],
                    text: "",
                };
            }
            return JSON.parse(jsonValue);
        }
        this.state = useState({
            fieldValue: fieldValue(this.props),
        });

        this.orm = useService("orm");
        this.action = useService("action");
    }

    buttonDefs() {
        return this.state.fieldValue.buttons;
    }

    text() {
        return this.state.fieldValue.text;
    }

    // hack: find a better way to get the record id
    recordId() {
        return this.state.fieldValue.record_id;
    }

    async executeTransition(button) {
        const action = {
            type: "object",
            resId: this.recordId(),
            name: button.action,
            resModel: this.props.record.resModel,
            context: button.context,
            onClose: async () => {
                await this.props.record.model.root.load();;
            }
        }
        await this.action.doActionButton(action);
    }
}

// see event_icon_selection
export const transitionButtons = {
    component: TransitionButtons,
    displayName: "Buttons",
    supportedTypes: ["char", "text", "selection"],
};

registry.category("fields").add("transition_buttons", transitionButtons);