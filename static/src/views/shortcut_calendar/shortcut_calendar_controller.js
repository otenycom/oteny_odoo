/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { ViewShortcutsBanner } from "@oteny_shortcut/components/view_shortcuts_banner/view_shortcuts_banner";

export class ShortcutCalendarController extends CalendarController {
    static template = "oteny_shortcut.ShortcutCalendarView";
    static components = {
        ...CalendarController.components,
        ViewShortcutsBanner,
    };
}
