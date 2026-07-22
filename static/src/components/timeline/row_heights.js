/** @odoo-module **/

/**
 * Shared row-height helpers for timeline virtual scrolling / unloaded spacers.
 *
 * Credential planning and crew planning use different geometry constants;
 * pass the view's constants into the helpers rather than hard-coding one set.
 */

/** Default geometry for the credential planning timeline. */
export const CRED_ROW_HEIGHT_CONSTANTS = {
    trackHeight: 21,
    trackGap: 1,
    trackPadding: 7, // top 3px + bottom 4px
};

/** Default geometry for the crew planning timeline. */
export const CREW_ROW_HEIGHT_CONSTANTS = {
    statusTrackHeight: 22,
    trackHeight: 20,
    trackGap: 1,
    verticalPadding: 12,
    borderHeight: 1,
    sectionHeaderHeight: 20,
};

/**
 * Credential-style row height from track count (no status track).
 *
 * @param {number} trackCount
 * @param {Object} [constants=CRED_ROW_HEIGHT_CONSTANTS]
 * @returns {number}
 */
export function rowHeightForTracks(trackCount, constants = CRED_ROW_HEIGHT_CONSTANTS) {
    const { trackHeight, trackGap, trackPadding } = constants;
    const single = trackHeight + trackPadding;
    if (trackCount <= 1) {
        return single;
    }
    return trackCount * trackHeight + (trackCount - 1) * trackGap + trackPadding;
}

/**
 * Crew-planning-style row height including the status track.
 *
 * @param {number} trackCount
 * @param {Object} [constants=CREW_ROW_HEIGHT_CONSTANTS]
 * @returns {number}
 */
export function calculateRowHeight(trackCount, constants = CREW_ROW_HEIGHT_CONSTANTS) {
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
        (trackCount - 1) * trackGap +
        verticalPadding +
        borderHeight
    );
}

/**
 * Cumulative heights per row, including section headers when the row type changes.
 *
 * @param {Array<Object>} rows
 * @param {function(Object): number} getTrackCount
 * @param {Object} [constants=CREW_ROW_HEIGHT_CONSTANTS]
 * @returns {Array<number>}
 */
export function calculateCumulativeHeights(
    rows,
    getTrackCount,
    constants = CREW_ROW_HEIGHT_CONSTANTS
) {
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
        cumulativeHeight += calculateRowHeight(getTrackCount(row), constants);
        heights.push(cumulativeHeight);
    }
    return heights;
}

/**
 * @param {Array<Object>} rows
 * @param {function(Object): number} getTrackCount
 * @param {Object} [constants=CREW_ROW_HEIGHT_CONSTANTS]
 * @returns {number}
 */
export function calculateTotalHeight(
    rows,
    getTrackCount,
    constants = CREW_ROW_HEIGHT_CONSTANTS
) {
    const heights = calculateCumulativeHeights(rows, getTrackCount, constants);
    return heights.length > 0 ? heights[heights.length - 1] : 0;
}

/**
 * Average per-row height excluding section headers — for unloaded-row spacers.
 *
 * @param {Array<Object>} rows
 * @param {function(Object): number} getTrackCount
 * @param {Object} [constants=CREW_ROW_HEIGHT_CONSTANTS]
 * @returns {number}
 */
export function calculateAverageRowHeight(
    rows,
    getTrackCount,
    constants = CREW_ROW_HEIGHT_CONSTANTS
) {
    if (rows.length === 0) {
        return 0;
    }
    let totalHeight = 0;
    for (const row of rows) {
        totalHeight += calculateRowHeight(getTrackCount(row), constants);
    }
    return totalHeight / rows.length;
}
