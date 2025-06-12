/* @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService, useBus } from "@web/core/utils/hooks";

const fieldRegistry = registry.category("fields");

// No changes needed in the renderer. It correctly triggers the event.
export class RiverflowOne2manyRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    get canResequenceRows() {
        // baseclass disallows drag and drop, if there is a sort order active on the list
        // but we want to allow it because after dropping a row, we want to re-sort the list server-side
        return true;
    }

    /**
     * @override
     */
    async sortDrop(dataRowId, { previous }) {
        const sourceRecord = this.props.list.records.find((rec) => rec.id === dataRowId);
        const sourceRecordId = sourceRecord ? sourceRecord.resId : null;

        if (!sourceRecordId) {
            this.notificationService.add("Cannot reorder an unsaved record.", { type: "warning" });
            return;
        }

        let targetRecordId = null;
        if (previous) {
            const targetRecord = this.props.list.records.find((rec) => rec.id === previous.dataset.id);
            targetRecordId = targetRecord ? targetRecord.resId : null;
        }

        try {
            await this.orm.call(
                this.props.list.resModel,
                "set_sub_sequence",
                [sourceRecordId],
                { target_id: targetRecordId }
            );

            await sourceRecord.model.root.load();

        } catch (e) {
            console.error("Could not reorder records:", e);
            this.notificationService.add("Failed to save the new order.", { type: "danger" });
        }
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
    ListRenderer: RiverflowOne2manyRenderer,
};