/** @odoo-module **/

import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { ReadOnlyCalendarPopover } from "./readonly_calendar_popover_component";

// Custom common renderer that uses our read-only popover
class ReadOnlyCalendarCommonRenderer extends CalendarCommonRenderer {
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: ReadOnlyCalendarPopover,
    };
}

// Main renderer that uses our custom common renderer for day/week/month views
export class ReadOnlyCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: ReadOnlyCalendarCommonRenderer,
        week: ReadOnlyCalendarCommonRenderer,
        month: ReadOnlyCalendarCommonRenderer,
    };
}
