import { registry } from "@web/core/registry";
import { StatusBarField, statusBarField } from "@web/views/fields/statusbar/statusbar_field";
import { _t } from "@web/core/l10n/translation";

const fieldRegistry = registry.category("fields");

export class RiverflowStatusBar extends StatusBarField {
    setup() {
        super.setup();
    }

    /**
     * Override the getAllItems method to provide custom status values
     * @override
     * @returns {Array}
     */
    getAllItems() {
        const statuses = this.props.record.data["state_id_statusbar_json"]["states"];
        if (!statuses) {
            // This happens in new-record mode, where the record is not saved yet
            return [];
        }
        return statuses;
    }
}

export const riverflowStatusBar = {
    ...statusBarField,
    component: RiverflowStatusBar,
};

fieldRegistry.add("riverflow_statusbar", riverflowStatusBar);