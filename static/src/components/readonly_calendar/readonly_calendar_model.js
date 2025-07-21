import { CalendarModel } from "@web/views/calendar/calendar_model";

export class ReadOnlyCalendarModel extends CalendarModel {
    setup(params, services) {
        super.setup(params, services);
    }
    computeDomain(data) {
        const domain = super.computeDomain(data);
        if (this.meta.fieldNames.includes("show_on_calendar")) {
            domain.push(['show_on_calendar', '=', true]);
        }
        return domain;
    }
}