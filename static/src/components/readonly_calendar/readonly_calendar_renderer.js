/** @odoo-module **/

import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { ReadOnlyCalendarPopover } from "./readonly_calendar_popover_component";
import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";

// Custom common renderer that uses our read-only popover
class ReadOnlyCalendarCommonRenderer extends CalendarCommonRenderer {
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: ReadOnlyCalendarPopover,
    };

    /**
     * @override
     */
    convertRecordToEvent(record) {
        const event = super.convertRecordToEvent(...arguments);
        // Pass the sort field to the FullCalendar event object.
        // We use `display_order` as the conventional field name.
        if (record.display_order !== undefined) {
            event.display_order = record.display_order;
        }
        return event;
    }

    /**
     * @override
     */
    get options() {
        const options = super.options;
        const sortField = 'res_sortable_name';

        // In month view, if the sort field is defined in the view's fields,
        // we prepend it to the `eventOrder` option of FullCalendar.
        if (
            this.props.model.scale === "month" &&
            this.props.model.meta.fieldNames.includes(sortField)
        ) {
            // Sort by the custom field first, then by the default sort order.
            options.eventOrder = `${sortField},start,-duration,allDay,title`;
        }
        return options;
    }
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