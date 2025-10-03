/** @odoo-module **/

import { CalendarCommonPopover } from "@web/views/calendar/calendar_common/calendar_common_popover";

export class ReadOnlyCalendarPopover extends CalendarCommonPopover {
    static template = "web.CalendarCommonPopover";

    /**
     * Override to always hide the footer with Edit/Delete buttons
     * @override
     */
    // get isEventEditable() {
    //     return false;
    // }
} 