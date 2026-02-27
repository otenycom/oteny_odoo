/** @odoo-module **/

import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar/calendar_view";
import { ShortcutCalendarController } from "./shortcut_calendar_controller";

export const shortcutCalendarView = {
    ...calendarView,
    Controller: ShortcutCalendarController,
};

registry.category("views").add("shortcut_calendar", shortcutCalendarView);
