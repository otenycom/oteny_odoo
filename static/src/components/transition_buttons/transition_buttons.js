/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillRender } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TransitionButtons extends Component {
    static template = "riverflow.TransitionButtons";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
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

    iconClass() {
        if (this.fieldValueState.workflow_icon)
            return "fa " + this.fieldValueState.workflow_icon;
        else return "";
    }

    text() {
        return this.fieldValueState.text;
    }

    reloadOnClose() {
        return this.fieldValueState.reload_on_close == true;
    }

    stateClass() {
        if (this.fieldValueState.is_end_state)
            return "riverflow_end_state";
        else return "riverflow_pending_state";
    }

    async saveRecord(node) {
        if (node.props.record) {
            await node.props.record.save();
        }
        // If we are in a Page on a notebook (tab page), we need to also save the parent record
        // as that may also have changes that need to be saved
        if (node.parent)
            await this.saveRecord(node.parent);
    }

    // Save the record in this component and all its parents
    async saveRecords() {
        await this.saveRecord(this.__owl__)
    }

    async executeTransition(button) {
        // Needed to prevent data loss due to the dialog being closed
        // as Cancelled or due to OK and .load() being called
        await this.saveRecords();

        const action = {
            type: "object",
            resId: this.props.record.resId,
            name: button.action,
            resModel: this.props.record.resModel,
            context: button.context,
            onClose: async () => {
                // We don't reload the root-data source for start transitions, 
                // as that's the start transition wizard's
                // and its closed by the time we need to reload the data
                if (this.reloadOnClose())
                    await this.props.record.model.root.load();
            }
        }
        await this.action.doActionButton(action);
    }
}

export const transitionButtons = {
    component: TransitionButtons,
    displayName: "Transition Buttons",
    supportedTypes: ["json"],
};

registry.category("fields").add("transition_buttons", transitionButtons);