/** @odoo-module **/

/**
 * Shared row-height helpers for timeline virtual scrolling / unloaded spacers.
 *
 * Formulas only — the geometry constants live with the view that owns them
 * (crew planning in `plan_timeline_track.js`, credential planning in its
 * renderer), so this module never has to know who its callers are. Each
 * helper therefore takes its constants explicitly; there is no default set,
 * because the two shapes are disjoint and silently defaulting to the wrong
 * one used to yield NaN.
 */

/**
 * Height of a row that is just N stacked tracks plus padding.
 *
 * @param {number} trackCount
 * @param {Object} constants
 * @param {number} constants.trackHeight
 * @param {number} constants.trackGap
 * @param {number} constants.trackPadding
 * @returns {number}
 */
export function stackedTracksHeight(trackCount, constants) {
    const { trackHeight, trackGap, trackPadding } = constants;
    const single = trackHeight + trackPadding;
    if (trackCount <= 1) {
        return single;
    }
    return trackCount * trackHeight + (trackCount - 1) * trackGap + trackPadding;
}

/**
 * Height of a row that carries a status track above its N stacked tracks,
 * plus vertical padding and a bottom border.
 *
 * @param {number} trackCount
 * @param {Object} constants
 * @param {number} constants.statusTrackHeight
 * @param {number} constants.trackHeight
 * @param {number} constants.trackGap
 * @param {number} constants.verticalPadding
 * @param {number} constants.borderHeight
 * @returns {number}
 */
export function statusTrackRowHeight(trackCount, constants) {
    const {
        statusTrackHeight,
        trackHeight,
        trackGap,
        verticalPadding,
        borderHeight,
    } = constants;
    return (
        statusTrackHeight +
        trackCount * trackHeight +
        // A single track has no gap to add; guard so a zero count cannot
        // subtract one (callers floor at 1, so this is insurance only).
        Math.max(0, trackCount - 1) * trackGap +
        verticalPadding +
        borderHeight
    );
}

/**
 * Cumulative heights per row, including section headers when the row type changes.
 *
 * @param {Array<Object>} rows
 * @param {function(Object): number} getTrackCount
 * @param {Object} constants - statusTrackRowHeight's constants + sectionHeaderHeight
 * @returns {Array<number>}
 */
export function calculateCumulativeHeights(rows, getTrackCount, constants) {
    if (rows.length === 0) {
        return [];
    }
    const { sectionHeaderHeight } = constants;
    const heights = [];
    let cumulativeHeight = 0;

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        if (i === 0 || rows[i - 1].type !== row.type) {
            cumulativeHeight += sectionHeaderHeight;
        }
        cumulativeHeight += statusTrackRowHeight(getTrackCount(row), constants);
        heights.push(cumulativeHeight);
    }
    return heights;
}

/**
 * Average per-row height excluding section headers — for unloaded-row spacers.
 *
 * @param {Array<Object>} rows
 * @param {function(Object): number} getTrackCount
 * @param {Object} constants
 * @returns {number}
 */
export function calculateAverageRowHeight(rows, getTrackCount, constants) {
    if (rows.length === 0) {
        return 0;
    }
    let totalHeight = 0;
    for (const row of rows) {
        totalHeight += statusTrackRowHeight(getTrackCount(row), constants);
    }
    return totalHeight / rows.length;
}
