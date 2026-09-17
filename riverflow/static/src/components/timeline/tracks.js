/** @odoo-module **/

/**
 * Vertical track assignment for overlapping timeline items.
 *
 * Consecutive items that share a boundary date (prev.end === next.start) are
 * treated as non-overlapping and share a track. Optional viewStart pruning
 * (crew planning) clears tracks that end before the visible window so old
 * items do not inflate the visible track count.
 */

/**
 * Assign trackIndex on each item in place.
 *
 * @param {Array<Object>} items - Items with start_date / end_date
 * @param {Object} opts
 * @param {function(string): luxon.DateTime} opts.parseDate
 * @param {luxon.DateTime|null} [opts.viewStart=null] - When set, prune tracks
 *   that end at/before the view start (crew planning behaviour)
 * @param {function(luxon.DateTime): luxon.DateTime|null} [opts.defaultEnd=null] -
 *   Fallback end when item has no end_date (crew planning uses +2 years).
 *   When null, items without end_date get trackIndex 0 and are skipped
 *   (credential planning behaviour).
 * @returns {Array<Object>} the same items array
 */
/**
 * First-fit track allocation: reuse the lowest track that is free at
 * itemStart, else open a new one. Mutates `tracks` (each entry is the end of
 * the item currently occupying that track, or null when free).
 *
 * @param {Array<luxon.DateTime|null>} tracks
 * @param {luxon.DateTime} itemStart
 * @param {luxon.DateTime} itemEnd
 * @returns {number} the assigned track index
 */
function claimFirstFreeTrack(tracks, itemStart, itemEnd) {
    for (let i = 0; i < tracks.length; i++) {
        const trackEnd = tracks[i];
        if (!trackEnd || itemStart >= trackEnd) {
            tracks[i] = itemEnd;
            return i;
        }
    }
    tracks.push(itemEnd);
    return tracks.length - 1;
}

export function assignVerticalTracks(
    items,
    { parseDate, viewStart = null, defaultEnd = null }
) {
    const tracks = [];

    for (const item of items) {
        if (!item.start_date) {
            item.trackIndex = 0;
            continue;
        }
        if (!item.end_date && !defaultEnd) {
            item.trackIndex = 0;
            continue;
        }

        const itemStart = parseDate(item.start_date);
        const itemEnd = item.end_date
            ? parseDate(item.end_date)
            : defaultEnd(itemStart);

        // Crew planning: items entirely before the view still get a track, but
        // later pruning clears tracks that end before viewStart.
        if (viewStart && itemEnd <= viewStart) {
            item.trackIndex = claimFirstFreeTrack(tracks, itemStart, itemEnd);
            continue;
        }

        if (viewStart) {
            for (let i = 0; i < tracks.length; i++) {
                if (tracks[i] && tracks[i] <= viewStart) {
                    tracks[i] = null;
                }
            }
        }

        item.trackIndex = claimFirstFreeTrack(tracks, itemStart, itemEnd);
    }

    return items;
}

/**
 * Number of visible tracks after assignment (at least 1).
 *
 * @param {Array<Object>} items
 * @param {Object} opts
 * @param {function(string): luxon.DateTime} opts.parseDate
 * @param {luxon.DateTime|null} [opts.viewStart=null]
 * @returns {number}
 */
export function calculateTrackCount(items, { parseDate, viewStart = null }) {
    if (!items.length) {
        return 1;
    }
    const visibleItems = viewStart
        ? items.filter((item) => {
              if (!item.end_date) {
                  return true;
              }
              return parseDate(item.end_date) > viewStart;
          })
        : items;
    if (!visibleItems.length) {
        return 1;
    }
    const maxTrack = Math.max(...visibleItems.map((item) => item.trackIndex || 0));
    return maxTrack + 1;
}
