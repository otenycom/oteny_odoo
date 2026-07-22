/** @odoo-module **/

/**
 * Shared timeline range / column maths for crew planning and credential planning.
 *
 * View-specific scale IDs (daily/weekly/monthly) stay in each model; this module
 * holds the pure window and column-loop logic that was duplicated byte-for-byte.
 */

/**
 * Build a planning window anchored on the start of the focus month.
 *
 * @param {luxon.DateTime} date - Focus date
 * @param {Object} opts
 * @param {number} [opts.startMonthOffset=0] - Months to shift the window start
 *   (e.g. -1 = start one month before the focus month)
 * @param {{ months?: number, years?: number }} opts.duration - Window length
 * @returns {{ startDate: luxon.DateTime, stopDate: luxon.DateTime }}
 */
export function getRangeWindow(date, { startMonthOffset = 0, duration }) {
    const startDate = date.startOf("month").plus({ month: startMonthOffset });
    const stopDate = duration.years
        ? startDate.plus({ year: duration.years }).minus({ day: 1 })
        : startDate.plus({ month: duration.months }).minus({ day: 1 });
    return { startDate, stopDate };
}

/**
 * Map a view scale id to a luxon interval unit.
 *
 * @param {string} rangeId
 * @param {Object.<string, string>} units - e.g. { weekly: "week", monthly: "month" }
 * @param {string} [fallback="week"]
 * @returns {string}
 */
export function getIntervalUnit(rangeId, units, fallback = "week") {
    return units[rangeId] || fallback;
}

/**
 * Build ordered column descriptors covering [startDate, stopDate].
 *
 * @param {luxon.DateTime} startDate
 * @param {luxon.DateTime} stopDate
 * @param {string} interval - luxon unit: "day" | "week" | "month"
 * @returns {Array<{ index: number, start: luxon.DateTime, end: luxon.DateTime, interval: string }>}
 */
export function calculateColumns(startDate, stopDate, interval) {
    const columns = [];

    let currentDate = startDate.startOf(interval);
    if (currentDate < startDate) {
        currentDate = startDate;
    }

    let index = 0;
    while (currentDate <= stopDate) {
        const columnEnd = currentDate.plus({ [interval]: 1 }).minus({ millisecond: 1 });
        const end = columnEnd > stopDate ? stopDate : columnEnd;
        columns.push({ index, start: currentDate, end, interval });
        currentDate = currentDate.plus({ [interval]: 1 });
        index++;
    }
    return columns;
}
