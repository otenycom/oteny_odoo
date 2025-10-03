/** @odoo-module **/

import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";
import { StateRecordCalendarRenderer } from "./state_record_calendar_renderer";

export const stateRecordCalendarView = {
    ...calendarView,
    Renderer: StateRecordCalendarRenderer,
};

registry.category("views").add("state_record_calendar", stateRecordCalendarView);