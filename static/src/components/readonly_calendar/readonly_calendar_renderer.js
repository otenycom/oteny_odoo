/** @odoo-module **/

import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";
import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { ReadOnlyCalendarPopover } from "./readonly_calendar_popover_component";

// Custom common renderer that uses our read-only popover and custom sorting
class ReadOnlyCalendarCommonRenderer extends CalendarCommonRenderer {
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: ReadOnlyCalendarPopover,
    };

    /**
     * @override
     */
    convertRecordToEvent(record) {
        const event = super.convertRecordToEvent(record);
        // Add the original Odoo record to the event object.
        // FullCalendar will automatically place this inside `extendedProps`.
        event.odooRecord = record;
        return event;
    }

    /**
     * @override
     */
    get options() {
        const defaultOptions = super.options;
        const sortFieldName = "res_sortable_name";
        // Only apply custom sorting for month view when the field is available.
        // this.props.model.scale !== "month" ||
        if (!this.props.model.meta.fieldNames.includes(sortFieldName)) {
            return defaultOptions;
        }

        return {
            ...defaultOptions,
            eventOrder: (eventA, eventB) => {
                const recordA = eventA.extendedProps.odooRecord;
                const recordB = eventB.extendedProps.odooRecord;

                // A basic fallback if records are missing for some reason.
                if (!recordA || !recordB) {
                    return eventA.title.localeCompare(eventB.title);
                }

                const orderA = recordA.rawRecord[sortFieldName];
                const orderB = recordB.rawRecord[sortFieldName];
                const hasOrderA = orderA !== undefined && orderA !== null;
                const hasOrderB = orderB !== undefined && orderB !== null;

                // If both records have a sort key, compare them.
                if (hasOrderA && hasOrderB) {
                    if (orderA < orderB) return -1;
                    if (orderA > orderB) return 1;
                }

                // If only one record has a sort key, it comes first.
                if (hasOrderA) return -1;
                if (hasOrderB) return 1;

                // If records have equal or no sort key, fall back to title comparison.
                return eventA.title.localeCompare(eventB.title);
            },
        };
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
