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
        this.timingDataState = {};
        onWillRender(() => {
            this.timingDataState = this.timingData();
        });
    }

    timingData() {
        const value = this.props.record.data[this.props.name];

        if (!value) {
            return {};
        }
        return value;
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
    supportedTypes: ["json"],
};

registry.category("fields").add("timing_widget", timingWidget);