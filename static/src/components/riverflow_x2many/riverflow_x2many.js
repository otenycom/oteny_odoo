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
        this.orm = useService("orm");
        this.notificationService = useService("notification");
    }

    get canResequenceRows() {
        // baseclass disallows drag and drop, if there is a sort order active on the list
        // but we want to allow it because after dropping a row, we want to re-sort the list server-side
        return true;
    }

    /**
     * @override
     */
    async sortDrop(id, { previous }) {
        const sourceRecord = this.props.list.records.find((rec) => rec.id === id);
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
                "handle_drop_event",
                [sourceRecordId],
                { target_id: targetRecordId }
            );

            // When used in an x2many, the list has a 'root' which is the form's model.
            // Reloading the root reloads the whole form view, including the x2many.
            // When used as a standalone list view, we just need to reload the list itself.
            if (this.props.list.root) {
                await this.props.list.root.load();
            } else {
                await this.props.list.load();
            }

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
    ListRenderer: RiverflowListRenderer,
};

export const riverflowServiceListView = {
    ...listView,
    Renderer: RiverflowListRenderer,
};

viewRegistry.add("riverflow_service_list", riverflowServiceListView);
