/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillRender, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TransitionButtons extends Component {
    static template = "riverflow.TransitionButtons";
    static props = {
        ...standardFieldProps,
        maxButtons: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.inputRef = useRef("inputElement");
        onWillRender(() => {
            this.fieldValueState = this.fieldValue(this.props);
        });
    }

    fieldValue(props) {
        const value = props.record.data[props.name];
        if (!value) {
            return {
                buttons: [],
                text: "",
            };
        }
        return value;
    }

    buttonDefs() {
        return this.fieldValueState.buttons;
    }

    buttonIconClass(button) {
        let class_name = "icon_span";
        if (button.icon)
            class_name += " fa " + button.icon;
        return class_name;
    }

    iconClass() {
        if (this.fieldValueState.workflow_icon)
            return "fa " + this.fieldValueState.workflow_icon;
        else return "";
    }

    useFullListLayout() {
        return this.fieldValueState.layout === "full_list";
    }

    text() {
        return this.fieldValueState.text;
    }

    datalistId() {
        return this.props.record.resModel + this.props.record.resId + "_transition_options";
    }

    reloadOnClose() {
        return this.fieldValueState.reload_on_close == true;
    }

    stateClass() {
        if (this.fieldValueState.is_end_state)
            return "riverflow_end_state";
        else return "riverflow_pending_state";
    }

    maxButtons() {
        return parseInt(this.props.maxButtons) || 2;
    }

    async saveRecord(node) {
        if (node.props.record) {
            await node.props.record.save();
        }
        if (node.parent)
            await this.saveRecord(node.parent);
    }

    async saveRecords() {
        await this.saveRecord(this.__owl__)
    }

    async onTransitionChange(event) {
        const selectedValue = event.target.value;
        const options = event.target.list.options;
        let selectedButton;

        for (let i = 0; i < options.length; i++) {
            if (options[i].value === selectedValue) {
                const buttonIndex = options[i].getAttribute('data-index');
                selectedButton = this.buttonDefs()[buttonIndex];
                break;
            }
        }

        if (selectedButton) {
            await this.executeTransition(selectedButton);
            // Clear the input after execution
            event.target.value = '';
        }
    }

    async executeTransition(button) {
        await this.saveRecords();

        const action = {
            type: "object",
            resId: this.props.record.resId,
            name: button.action,
            resModel: this.props.record.resModel,
            context: button.context,
            onClose: async () => {
                if (this.reloadOnClose())
                    await this.props.record.model.root.load();
            }
        }
        await this.action.doActionButton(action);
    }

    onSpanClick() {
        const inputElement = this.inputRef.el;
        if (inputElement) {
            inputElement.focus();
            inputElement.click();
        }
    }
}

export const transitionButtons = {
    component: TransitionButtons,
    displayName: "Transition Buttons",
    supportedTypes: ["json"],
    extractProps: ({ attrs, options, viewType }, dynamicInfo) => ({
        maxButtons: attrs.max_buttons || "2"
    }),
};

registry.category("fields").add("transition_buttons", transitionButtons);