/** @odoo-module **/

import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";
import { StateRecordCalendarRenderer } from "./state_record_calendar_renderer";
import { StateRecordCalendarController } from "./state_record_calendar_controller";

export const stateRecordCalendarView = {
    ...calendarView,
    Controller: StateRecordCalendarController,
    Renderer: StateRecordCalendarRenderer,
};

registry.category("views").add("state_record_calendar", stateRecordCalendarView);