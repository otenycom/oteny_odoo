/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DynamicButtons extends Component {
    // Consider refactoring this class similar to hr_expense.ListButtons
    // or wrap the buttons in a popover, to fit an unlimited number of buttons
    static template = "riverflow.DynamicButtons";
    static props = {
        ...standardFieldProps,
        buttons: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    fieldValue() {
        const jsonValue = this.props.record.data[this.props.name];

        if (!jsonValue) {
            return {
                buttons: [],
                text: "",
            };
        }
        return JSON.parse(jsonValue);
    }

    buttonDefs() {
        return this.fieldValue().buttons;
    }

    text() {
        return this.fieldValue().text;
    }

    recordId() {
        return this.fieldValue().record_id;
    }

    async executeTransition(button) {
        const action = {
            type: "object",
            resId: this.recordId(),
            name: "action_button_click",
            resModel: 'riverflow.service',
            context: button.context,
            onClose: async () => {
                await this.props.record.model.root.load();;
            }
        }
        await this.action.doActionButton(action);
    }
}

// see event_icon_selection
export const dynamicButtons = {
    component: DynamicButtons,
    displayName: "Buttons",
    supportedTypes: ["char", "text", "selection"],
};

registry.category("fields").add("dynamic_buttons", dynamicButtons);