/** @odoo-module **/

import { getRangeWindow } from "./range";
import { resolveCustomRange } from "./range_state";

const { DateTime } = luxon;

/**
 * Timeline window ⇄ shortcut layout.
 *
 * A saved Favorite promoted to a shortcut button (oteny_shortcut) can carry a
 * view layout. For a planning timeline that layout is the period the user
 * wants to land on, so a shortcut becomes a one-click "Passports, next six
 * months" filter. Layout keys (JSON on ir.filters.shortcut_layout):
 *
 *   range_id         "monthly" | "weekly" | "daily" | "custom" — the view's
 *                    own scale ids; a scale means "its default window around
 *                    today", so such a shortcut stays current
 *   start_date /     ISO dates of a fixed custom period
 *   stop_date
 *   relative_period  { start_month_offset, months } — a custom period in
 *                    whole months from the start of today's month; the same
 *                    window shape the scales use (getRangeWindow). Wins over
 *                    fixed dates when both are present. The Store Layout
 *                    wizard writes it when the user picks "Relative to today".
 *
 * Only the pure conversions live here; which scale ids exist and how a custom
 * window is clamped stay in each view's model, injected as callbacks.
 */

/**
 * @param {{ rangeId: string, startDate: luxon.DateTime, stopDate: luxon.DateTime }} range
 * @returns {Object} layout keys for the current window
 */
export function layoutFromRange({ rangeId, startDate, stopDate }) {
    const layout = { range_id: rangeId };
    if (rangeId === "custom" && startDate && stopDate) {
        layout.start_date = startDate.toISODate();
        layout.stop_date = stopDate.toISODate();
    }
    return layout;
}

/**
 * @param {Object|null} layout - parsed shortcut layout
 * @param {Object} opts
 * @param {luxon.DateTime} opts.today
 * @param {function(string, luxon.DateTime): Object} opts.getRangeFromDate - the
 *   view's scale → window mapping ({focusDate, startDate, stopDate, rangeId})
 * @param {function(luxon.DateTime, luxon.DateTime): {startDate, stopDate}} [opts.clampWindow]
 * @returns {{focusDate, startDate, stopDate, rangeId}|null} params for the
 *   model's fetchData, or null when the layout carries no usable period
 */
export function rangeParamsFromLayout(layout, { today, getRangeFromDate, clampWindow }) {
    const rangeId = layout?.range_id;
    if (!rangeId) {
        return null;
    }
    if (rangeId !== "custom") {
        return getRangeFromDate(rangeId, today);
    }

    let startDate = null;
    let stopDate = null;
    const relative = layout.relative_period;
    if (relative && Number.isInteger(relative.months) && relative.months > 0) {
        ({ startDate, stopDate } = getRangeWindow(today, {
            startMonthOffset: relative.start_month_offset || 0,
            duration: { months: relative.months },
        }));
    } else if (layout.start_date && layout.stop_date) {
        startDate = DateTime.fromISO(layout.start_date);
        stopDate = DateTime.fromISO(layout.stop_date);
        if (!startDate.isValid || !stopDate.isValid) {
            return null;
        }
        startDate = startDate.startOf("day");
        stopDate = stopDate.startOf("day");
    } else {
        return null;
    }
    return resolveCustomRange({ startDate, stopDate, focusDate: today, clampWindow });
}
