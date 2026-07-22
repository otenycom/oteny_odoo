/** @odoo-module **/

/**
 * Percentage-based horizontal item positioning shared by timeline views.
 *
 * Vertical track offset is parameterized so each view keeps its own track
 * geometry (credential bars vs crew planning status-track + item tracks).
 */

/**
 * Compute left/width percentages for an item clamped to the timeline window.
 *
 * @param {Object} opts
 * @param {number} opts.itemStartMs
 * @param {number} opts.itemEndMs
 * @param {number} opts.timelineStartMs
 * @param {number} opts.timelineDurationMs
 * @param {number} [opts.minWidthPct=0.3]
 * @returns {{ leftPct: number, widthPct: number } | null} null when fully outside
 */
export function getItemPctPosition({
    itemStartMs,
    itemEndMs,
    timelineStartMs,
    timelineDurationMs,
    minWidthPct = 0.3,
}) {
    if (!timelineDurationMs) {
        return null;
    }
    const tlEndMs = timelineStartMs + timelineDurationMs;
    const visStart = Math.max(itemStartMs, timelineStartMs);
    const visEnd = Math.min(itemEndMs, tlEndMs);
    if (visStart >= visEnd) {
        return null;
    }
    const leftPct = ((visStart - timelineStartMs) / timelineDurationMs) * 100;
    const widthPct = Math.max(
        minWidthPct,
        ((visEnd - visStart) / timelineDurationMs) * 100
    );
    return { leftPct, widthPct };
}

/**
 * Build the CSS position style string for a timeline item bar.
 *
 * @param {Object} opts - Same as getItemPctPosition, plus vertical geometry
 * @param {number} [opts.trackIndex=0]
 * @param {number} opts.trackHeight
 * @param {number} opts.trackGap
 * @param {number} opts.topOffset - Pixels above track 0 (status track, padding, …)
 * @returns {string}
 */
export function getItemPositionStyle(opts) {
    const pos = getItemPctPosition(opts);
    if (!pos) {
        return "display: none;";
    }
    const trackIndex = opts.trackIndex || 0;
    const topPx =
        opts.topOffset + trackIndex * (opts.trackHeight + opts.trackGap);
    return (
        `left: ${pos.leftPct}%; width: ${pos.widthPct}%; ` +
        `top: ${topPx}px; height: ${opts.trackHeight}px;`
    );
}
