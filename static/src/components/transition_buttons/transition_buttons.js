/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TransitionButtons extends Component {
    // Consider refactoring this class similar to hr_expense.ListButtons
    // or wrap the buttons in a popover, to fit an unlimited number of buttons
    static template = "riverflow.TransitionButtons";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        //this.updateStateFromProps(this.props);
        //onWillUpdateProps((props) => this.updateStateFromProps(props));

        this.orm = useService("orm");
        this.action = useService("action");
    }

    // updateStateFromProps(props) {
    //     this.state = useState({
    //         fieldValue: fieldValue(props),
    //     });
    // }

    // returns 'transition_buttons_json' field value
    fieldValue(props) {
        const jsonValue = props.record.data[props.name];

        if (jsonValue === undefined || jsonValue === "") {
            return {
                buttons: [],
                text: "",
            };
        }
        return JSON.parse(jsonValue);
    }

    buttonDefs() {
        //return this.state.fieldValue.buttons;
        return this.fieldValue(this.props).buttons;
    }

    iconClass() {
        if (this.fieldValue(this.props).workflow_icon)
            return "fa " + this.fieldValue(this.props).workflow_icon;
        else return "";
    }

    text() {
        return this.fieldValue(this.props).text;
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
            resId: this.props.record.resId, //this.recordId(),
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
    displayName: "Transition Buttons",
    supportedTypes: ["char", "text", "selection"],
};

registry.category("fields").add("transition_buttons", transitionButtons);