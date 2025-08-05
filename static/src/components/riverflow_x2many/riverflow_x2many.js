/* @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";

const fieldRegistry = registry.category("fields");
const viewRegistry = registry.category("views");


export class RiverflowListRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

}


export class RiverflowOne2many extends X2ManyField {
    setup() {
        super.setup();
        this.actionService = useService("action");

        this._openRecord = async (params) => {
            const parentRecord = this.props.record;
            if (!await parentRecord.save()) {
                return;
            }
            const { record } = params;
            if (!record) {
                throw new Error("Don't use a `riverflow_one2many` widget with no_create=false.");
            }
            const action = {
                type: "ir.actions.act_window",
                target: "current",
                view_mode: "form",
                views: [[false, "form"]],
                res_id: record.resId,
                res_model: record.resModel,
                context: record.context,
            }
            await this.actionService.doAction(action);
        };
        this.canOpenRecord = true;
    }
}

export const riverflowOne2many = {
    ...x2ManyField,
    component: RiverflowOne2many,
};

fieldRegistry.add("riverflow_one2many", riverflowOne2many);

RiverflowOne2many.components = {
    ...X2ManyField.components,
    ListRenderer: RiverflowListRenderer,
};

export const riverflowServiceListView = {
    ...listView,
    Renderer: RiverflowListRenderer,
};

viewRegistry.add("riverflow_service_list", riverflowServiceListView);
