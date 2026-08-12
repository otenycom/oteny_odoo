/** @odoo-module **/

/**
 * Range navigation shared by the timeline plan views.
 *
 * Pure functions over a `{focusDate, rangeId, startDate, stopDate}` state.
 * Each returns only the keys it changed, so callers keep their own
 * `Object.assign(this.state, ...)` and OWL reactivity is untouched.
 *
 * The views differ in three ways, so those three are injected and nothing
 * else: how far a scaled step moves (`stepMonths`), what window a scale maps
 * to (`getRangeFromDate`), and how a custom window is constrained
 * (`clampWindow`). Scale ids never enter this module.
 */

/**
 * Slide the window one page in `direction`.
 *
 * A custom range slides by its own span, staying contiguous with the window
 * it left (hence the +1: the span is inclusive of both end dates). A scaled
 * range is re-derived from a focus date stepped by `stepMonths`.
 *
 * @param {Object} state - {focusDate, rangeId, startDate, stopDate}
 * @param {"next"|"previous"} direction
 * @param {Object} opts
 * @param {number} opts.stepMonths - months per step for the current scale
 * @param {function(string, luxon.DateTime): Object} opts.getRangeFromDate
 * @returns {Object} the changed state keys
 */
export function stepRangeWindow(state, direction, { stepMonths, getRangeFromDate }) {
    const sign = direction === "next" ? 1 : -1;
    const { focusDate, rangeId, startDate, stopDate } = state;

    if (rangeId === "custom") {
        const days = stopDate.diff(startDate, "day").days + 1;
        return {
            focusDate: focusDate.plus({ day: sign * days }),
            startDate: startDate.plus({ day: sign * days }),
            stopDate: stopDate.plus({ day: sign * days }),
        };
    }
    return getRangeFromDate(rangeId, focusDate.plus({ month: sign * stepMonths }));
}

/**
 * Re-centre the window on `today`.
 *
 * A custom range keeps its exact span (note: no +1 here — unlike a page step,
 * re-centring preserves the window rather than tiling the next one). A scaled
 * range is re-derived around today.
 *
 * @param {Object} state - {rangeId, startDate, stopDate}
 * @param {luxon.DateTime} today
 * @param {Object} opts
 * @param {function(string, luxon.DateTime): Object} opts.getRangeFromDate
 * @returns {Object} the changed state keys
 */
export function recenterRangeWindow(state, today, { getRangeFromDate }) {
    const { rangeId, startDate, stopDate } = state;

    if (rangeId !== "custom") {
        return { focusDate: today, ...getRangeFromDate(rangeId, today) };
    }
    const days = stopDate.diff(startDate, "day").days;
    if (days === 0) {
        return { focusDate: today, startDate: today, stopDate: today };
    }
    const before = Math.floor(days / 2);
    return {
        focusDate: today,
        startDate: today.minus({ day: before }),
        stopDate: today.plus({ day: days - before }),
    };
}

/**
 * Resolve a stored or context-supplied custom range into a usable window.
 *
 * Returns null when there is no usable custom range, so the caller can fall
 * back to its own default scale.
 *
 * @param {Object} opts
 * @param {luxon.DateTime|null} opts.startDate
 * @param {luxon.DateTime|null} opts.stopDate
 * @param {luxon.DateTime} opts.focusDate
 * @param {function(luxon.DateTime, luxon.DateTime): {startDate, stopDate}} [opts.clampWindow]
 * @returns {{focusDate, startDate, stopDate, rangeId: "custom"}|null}
 */
export function resolveCustomRange({ startDate, stopDate, focusDate, clampWindow }) {
    // One-sided input: assume a one-year window on the given side.
    if (startDate && !stopDate) {
        stopDate = startDate.plus({ year: 1 }).minus({ day: 1 });
    } else if (!startDate && stopDate) {
        startDate = stopDate.minus({ year: 1 });
    }
    if (startDate && stopDate && clampWindow) {
        ({ startDate, stopDate } = clampWindow(startDate, stopDate));
    }
    if (!startDate || !stopDate || startDate > stopDate) {
        return null;
    }
    // Keep the focus inside the window so navigation steps from it.
    if (focusDate < startDate) {
        focusDate = startDate;
    } else if (focusDate > stopDate) {
        focusDate = stopDate;
    }
    return { focusDate, startDate, stopDate, rangeId: "custom" };
}
