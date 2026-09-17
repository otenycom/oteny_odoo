/** @odoo-module **/

import { useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { CalendarController } from "@web/views/calendar/calendar_controller";

// Why this exists:
// The shortcut banner (rendered by Layout on every calendar view) can store
// and restore a calendar layout: the scale and the weekend visibility. The
// calendar controller owns those, so it exposes getViewLayout and
// applyViewLayout to the banner through env.shortcutLayout. This used to be
// the ShortcutCalendarController behind js_class="shortcut_calendar".
patch(CalendarController.prototype, {
    setup() {
        super.setup();
        useSubEnv({
            shortcutLayout: {
                getViewLayout: () => this.getViewLayout(),
                applyViewLayout: (layout) => this.applyViewLayout(layout),
            },
        });
    },

    /**
     * Capture the current calendar layout: scale and weekend visibility.
     */
    getViewLayout() {
        return {
            scale: this.model.scale,
            show_weekends: this.state.isWeekendVisible,
        };
    },

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
        if (
            layout.show_weekends !== undefined &&
            layout.show_weekends !== this.state.isWeekendVisible
        ) {
            this.toggleWeekendVisibility();
        }
    },
});
