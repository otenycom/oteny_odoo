/** @odoo-module **/

import { CalendarCommonPopover } from "@web/views/calendar/calendar_common/calendar_common_popover";
import { useService } from "@web/core/utils/hooks";

export class StateRecordCalendarPopover extends CalendarCommonPopover {
    static template = "web.CalendarCommonPopover";

    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    /**
     * Override to open the master record instead of the state record
     * when clicking View/Edit in the popover footer.
     * This calls the action_view_master_record method which returns an action
     * to open the related resource (log entry, service, etc.).
     * @override
     */
    async onEditEvent() {
        // Call the Python method to get the action for opening the master record
        const action = await this.props.model.orm.call(
            this.props.model.resModel,
            "action_view_master_record",
            [[this.props.record.id]]
        );

        // Close the popover and execute the action
        this.props.close();
        this.actionService.doAction(action);
    }
} 