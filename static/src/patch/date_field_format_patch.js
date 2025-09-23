import { DateTimeField } from "@web/views/fields/datetime/datetime_field";
import { patch } from "@web/core/utils/patch";
import { formatDate } from "@web/views/fields/formatters";
import { exprToBoolean } from "@web/core/utils/strings";

patch(DateTimeField.prototype, {
    getFormattedValue(valueIndex, numeric) {
        // Always force numeric to true, ignore whatever was passed
        return super.getFormattedValue(valueIndex, true);
    }
});

patch(formatDate, {
    extractOptions: ({ options }) => ({
        numeric: exprToBoolean(options.numeric ?? true),
    })
});

