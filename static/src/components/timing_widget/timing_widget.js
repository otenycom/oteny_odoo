/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillRender } from "@odoo/owl";

export class TimingWidget extends Component {
    static template = "riverflow.TimingWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        //this.timingDataState = this.timingData();

        onWillRender(() => {
            this.timingDataState = this.timingData();
        });
    }

    timingData() {
        // hack: get the timing data from the timing_widget_json field
        // by binding the widget to the normal timing field, we ensure the popup tooltip shows the normal text  
        const jsonValue = this.props.record.data[this.props.name + "_widget_json"];

        if (jsonValue === undefined || jsonValue === "") {
            return {};
        }
        return JSON.parse(jsonValue);
    }

    get relativedays() {
        return this.timingDataState.relative_days || "";
    }

    get date() {
        return this.timingDataState.date || "";
    }

    get daysRemaining() {
        return this.timingDataState.days_remaining;
    }

    get dateClass() {
        if (this.timingDataState.is_past) return "riverflow_is_past";
        if (this.timingDataState.is_today) return "riverflow_is_today";
        return "";
    }
}

export const timingWidget = {
    component: TimingWidget,
    supportedTypes: ["char"],
};

registry.category("fields").add("timing_widget", timingWidget);