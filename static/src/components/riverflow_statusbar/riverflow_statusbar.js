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
        // fetch the states from field state_id_statusbar_json
        const customStatuses = this.props.record.data["state_id_statusbar_json"]["states"];

        // // Sample hardcoded status values
        // const customStatuses = [
        //     { value: 'draft', label: _t('Draft'), isFolded: false },
        //     { value: 'confirmed', label: _t('Confirmed'), isFolded: false },
        //     { value: 'in_progress', label: _t('In Progress'), isFolded: false },
        //     { value: 'done', label: _t('Done'), isFolded: false },
        //     { value: 'cancelled', label: _t('Cancelled'), isFolded: true },
        // ];

        const currentValue = this.props.record.data[this.props.name];

        return customStatuses;
        // .map(status => ({
        //     ...status,
        //     isSelected: status.value === currentValue,
        // }));
    }
}

export const riverflowStatusBar = {
    ...statusBarField,
    component: RiverflowStatusBar,
};

fieldRegistry.add("riverflow_statusbar", riverflowStatusBar);