/** @odoo-module **/

import { onWillUpdateProps, useState } from "@odoo/owl";
import { useDateTimePicker } from "@web/core/datetime/datetime_picker_hook";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { formatDate } from "@web/core/l10n/dates";
import { usePopover } from "@web/core/popover/popover_hook";
import { ViewScaleSelector } from "@web/views/view_components/view_scale_selector";

const { DateTime } = luxon;

/**
 * TimelineScaleSelector
 *
 * Scale dropdown shared by the crew planning and credential planning
 * timelines. Renders the view's scales plus a "custom" entry with From/to
 * date pickers and an Apply button.
 *
 * Consumers pass the current window (startDate/stopDate) and a
 * selectCustomRange callback. Optional minDate/maxDate clamp the pickers to
 * the window where data actually exists (credential planning's server-side
 * horizon); without them the pickers only enforce the 10-year span cap.
 */
export class TimelineScaleSelector extends ViewScaleSelector {
    static template = "riverflow.TimelineScaleSelector";

    static props = {
        ...ViewScaleSelector.props,
        startDate: DateTime,
        stopDate: DateTime,
        selectCustomRange: Function,
        minDate: { type: DateTime, optional: true },
        maxDate: { type: DateTime, optional: true },
    };

    setup() {
        super.setup();

        this.pickerValues = useState({
            startDate: this.props.startDate,
            stopDate: this.props.stopDate,
        });

        onWillUpdateProps((nextProps) => {
            // Only sync when the applied window actually changed. The parent
            // timelines re-render constantly (hover state, model notify deep
            // renders bypass Owl's prop-equality skip), so an unconditional
            // sync here would wipe an un-applied picker selection the moment
            // the mouse touches the timeline.
            if (+nextProps.startDate !== +this.props.startDate) {
                this.pickerValues.startDate = nextProps.startDate;
            }
            if (+nextProps.stopDate !== +this.props.stopDate) {
                this.pickerValues.stopDate = nextProps.stopDate;
            }
        });

        const getPickerProps = (key) => {
            const pickerProps = { type: "date", value: this.pickerValues[key] };
            if (this.props.minDate) {
                pickerProps.minDate = this.props.minDate;
            }
            if (this.props.maxDate) {
                pickerProps.maxDate = this.props.maxDate;
            }
            return pickerProps;
        };

        this.startPicker = useDateTimePicker({
            target: "start-picker",
            onApply: (date) => {
                this.pickerValues.startDate = date;
                if (this.pickerValues.stopDate < date) {
                    this.pickerValues.stopDate = date;
                } else if (date.plus({ year: 10, day: -1 }) < this.pickerValues.stopDate) {
                    this.pickerValues.stopDate = date.plus({ year: 10, day: -1 });
                }
            },
            get pickerProps() {
                return getPickerProps("startDate");
            },
            createPopover: (...args) => usePopover(...args),
            ensureVisibility: () => false,
        });

        this.stopPicker = useDateTimePicker({
            target: "stop-picker",
            onApply: (date) => {
                this.pickerValues.stopDate = date;
                if (date < this.pickerValues.startDate) {
                    this.pickerValues.startDate = date;
                } else if (this.pickerValues.startDate.plus({ year: 10, day: -1 }) < date) {
                    this.pickerValues.startDate = date.minus({ year: 10, day: -1 });
                }
            },
            get pickerProps() {
                return getPickerProps("stopDate");
            },
            createPopover: (...args) => usePopover(...args),
            ensureVisibility: () => false,
        });

        this.dropdownState = useDropdownState();
    }

    /**
     * Format a date for display
     */
    getFormattedDate(date) {
        return formatDate(date);
    }

    /**
     * Apply the custom date range
     */
    onApply() {
        let { startDate, stopDate } = this.pickerValues;
        // Defensive horizon clamp — the pickers already disable out-of-bounds
        // days, but the values can also arrive via the mutual-clamping logic
        if (this.props.minDate && startDate < this.props.minDate) {
            startDate = this.props.minDate;
        }
        if (this.props.maxDate && stopDate > this.props.maxDate) {
            stopDate = this.props.maxDate;
        }
        this.props.selectCustomRange(startDate, stopDate);
        this.dropdownState.close();
    }
}
