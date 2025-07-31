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

        return {
            ...defaultOptions,
            eventOrder: (eventA, eventB) => {
                const recordA = eventA.extendedProps.odooRecord;
                const recordB = eventB.extendedProps.odooRecord;

                // A basic fallback if records are missing for some reason.
                if (!recordA || !recordB) {
                    return eventA.title.localeCompare(eventB.title);
                }

                const rawA = recordA.rawRecord;
                const rawB = recordB.rawRecord;

                const compareField = (fieldName, order = "asc") => {
                    const valA = rawA[fieldName];
                    const valB = rawB[fieldName];
                    const hasValA = valA !== undefined && valA !== null;
                    const hasValB = valB !== undefined && valB !== null;

                    // Records with a value come before records without a value.
                    if (hasValA && !hasValB) return -1;
                    if (!hasValA && hasValB) return 1;
                    if (!hasValA && !hasValB) return 0;

                    let result = 0;
                    if (typeof valA === "string" && typeof valB === "string") {
                        result = valA.localeCompare(valB);
                    } else if (valA < valB) {
                        result = -1;
                    } else if (valA > valB) {
                        result = 1;
                    }

                    if (order === "desc") {
                        result *= -1;
                    }

                    return result;
                };

                const sortCriteria = [
                    { name: "res_date" },
                    { name: "res_model" },
                    { name: "res_sortable_name" },
                    { name: "res_id" },
                    { name: "is_subject", order: "desc" },
                    { name: "root_name" },
                    { name: "root_id" },
                    { name: "display_order" },
                    { name: "deadline" },
                ];

                for (const criteria of sortCriteria) {
                    const result = compareField(criteria.name, criteria.order);
                    if (result !== 0) {
                        return result;
                    }
                }

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
