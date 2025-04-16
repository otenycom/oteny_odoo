/* @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService } from "@web/core/utils/hooks";

const fieldRegistry = registry.category("fields");

export class RiverflowOne2manyRenderer extends ListRenderer {
    setup() {
        super.setup();
    }
}

export class RiverflowOne2many extends X2ManyField {
    /**
     * Overrides the "openRecord" method so that it opens the child record in a normal form view
     * instead of in a dialog. This way the user can see the chatter of the child record.
     */
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
    ListRenderer: RiverflowOne2manyRenderer,
};
