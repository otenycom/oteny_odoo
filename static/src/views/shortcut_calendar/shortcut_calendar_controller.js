/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { ViewShortcutsBanner } from "@oteny_shortcut/components/view_shortcuts_banner/view_shortcuts_banner";

export class ShortcutCalendarController extends CalendarController {
    static template = "oteny_shortcut.ShortcutCalendarView";
    static components = {
        ...CalendarController.components,
        ViewShortcutsBanner,
    };

    /**
     * Capture the current calendar layout: scale and weekend visibility.
     */
    getViewLayout() {
        return {
            scale: this.model.scale,
            show_weekends: this.state.isWeekendVisible,
        };
    }

    /**
     * Restore a stored calendar layout by setting the scale and
     * weekend visibility to match the stored values.
     */
    applyViewLayout(layout) {
        if (!layout) {
            return;
        }
        if (layout.scale && layout.scale !== this.model.scale) {
            this.setScale(layout.scale);
        }
        if (layout.show_weekends !== undefined && layout.show_weekends !== this.state.isWeekendVisible) {
            this.toggleWeekendVisibility();
        }
    }
}
