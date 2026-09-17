/* @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";

const fieldRegistry = registry.category("fields");
const viewRegistry = registry.category("views");


/**
 * Extended ListRenderer that supports storage_key_suffix for independent column visibility settings.
 * @extends ListRenderer
 */
export class RiverflowListRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    /**
     * Override to include storage_key_suffix from nestedKeyOptionalFieldsData.
     * This allows multiple instances of the same field to have independent column settings.
     */
    createViewKey() {
        const baseKey = super.createViewKey();
        // @ts-ignore - props is available from parent Component class
        const suffix = this.props.nestedKeyOptionalFieldsData?.storage_key_suffix;
        if (suffix) {
            return `${baseKey},${suffix}`;
        }
        return baseKey;
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

    /**
     * Override to include storage_key_suffix from context.
     * This allows multiple instances of the same field to have independent column settings.
     */
    get nestedKeyOptionalFieldsData() {
        const baseData = super.nestedKeyOptionalFieldsData;
        const storageKeySuffix = this.props.context?.storage_key_suffix;

        if (storageKeySuffix) {
            return {
                ...baseData,
                storage_key_suffix: storageKeySuffix,
            };
        }
        return baseData;
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
