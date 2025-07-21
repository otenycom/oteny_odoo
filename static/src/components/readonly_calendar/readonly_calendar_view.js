/** @odoo-module **/

import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";
import { ReadOnlyCalendarRenderer } from "./readonly_calendar_renderer";
import { ReadOnlyCalendarModel } from "./readonly_calendar_model";

export const readOnlyCalendarView = {
    ...calendarView,
    Renderer: ReadOnlyCalendarRenderer,
    Model: ReadOnlyCalendarModel,
};

registry.category("views").add("readonly_calendar", readOnlyCalendarView);