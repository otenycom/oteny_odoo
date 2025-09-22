import { DateTimeField } from "@web/views/fields/datetime/datetime_field";
import { patch } from "@web/core/utils/patch";

patch(DateTimeField.prototype, {
    getFormattedValue(valueIndex, numeric) {
        // Always force numeric to true, ignore whatever was passed
        return super.getFormattedValue(valueIndex, true);
    }
});