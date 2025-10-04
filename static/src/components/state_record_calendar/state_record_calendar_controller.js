/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { useService } from "@web/core/utils/hooks";

export class StateRecordCalendarController extends CalendarController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    /**
     * Override editRecord to open the master record instead of the state record.
     * When double-clicking on a calendar event, open the related service or log entry
     * rather than the state record itself.
     */
    async editRecord(record, context = {}) {
        // Call the Python method to get the action for opening the master record
        const action = await this.orm.call(
            this.model.resModel,
            "action_view_master_record",
            [[record.id]]
        );

        // Execute the action to open the master record
        await this.actionService.doAction(action);
    }

    /**
     * Override createRecord to create a service instead of a state record.
     * State records are derived/denormalized records that are automatically
     * created when services are created via the tracker mixin.
     * 
     * When a user creates an item in the calendar, we open a service form
     * with the start and end dates pre-filled from the calendar.
     */
    createRecord(record) {
        if (!this.model.canCreate) {
            return;
        }

        // Extract the dates from the calendar click/drag
        const context = {
            default_use_project_deadline_from: "self",
        };

        if (record && record.start) {
            // Set project_deadline to the clicked/dragged start date
            context.default_project_deadline = record.start.toFormat("yyyy-MM-dd");

            // If there's an end date and it's different from start, set it
            // The form uses the daterange widget with 'end_date' field
            if (record.end && !record.start.hasSame(record.end, "day")) {
                context.default_end_date = record.end.toFormat("yyyy-MM-dd");
            }
        }

        // Open a service creation form
        return new Promise((resolve) => {
            this.displayDialog(
                FormViewDialog,
                {
                    resModel: "riverflow.service",
                    context: context,
                    title: "New Service",
                    onRecordSaved: async () => {
                        // Reload the calendar to show the newly created service's state record
                        await this.model.load();
                        resolve();
                    },
                },
                {
                    onClose: () => resolve(),
                }
            );
        });
    }
}

