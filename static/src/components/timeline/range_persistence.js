/** @odoo-module **/

/**
 * (De)serialization of the persisted timeline range selection.
 *
 * The chosen scale — and, for custom ranges, the chosen dates — is remembered
 * per view in localStorage. Historically only the bare rangeId string was
 * stored (e.g. "weekly"), which meant a custom range silently degraded to the
 * default scale on the next load() (page reload or any search/filter change).
 * The JSON format stores the custom dates alongside the rangeId so the range
 * survives; parseStoredRange still accepts the legacy bare-string values.
 *
 * Only syntactic validation happens here (parseable, valid dates, start
 * before stop). Policy validation — is the rangeId one of the view's scales,
 * span caps, data-horizon clamping — stays in each view's model, which owns
 * those rules.
 */

const { DateTime } = luxon;

/**
 * @param {{ rangeId: string, startDate?: luxon.DateTime, stopDate?: luxon.DateTime }} range
 * @returns {string} JSON string for localStorage
 */
export function serializeStoredRange({ rangeId, startDate, stopDate }) {
    const stored = { rangeId };
    if (rangeId === "custom" && startDate && stopDate) {
        stored.startDate = startDate.toISODate();
        stored.stopDate = stopDate.toISODate();
    }
    return JSON.stringify(stored);
}

/**
 * @param {string|null} raw - Raw localStorage value (JSON or legacy bare rangeId)
 * @returns {{ rangeId: string, startDate?: luxon.DateTime, stopDate?: luxon.DateTime }|null}
 */
export function parseStoredRange(raw) {
    if (!raw) {
        return null;
    }
    let stored;
    try {
        stored = JSON.parse(raw);
    } catch {
        // Legacy format: the bare rangeId string (not valid JSON)
        return { rangeId: raw };
    }
    if (typeof stored === "string") {
        // e.g. a quoted string that happened to be valid JSON
        return { rangeId: stored };
    }
    if (!stored || typeof stored !== "object" || typeof stored.rangeId !== "string") {
        return null;
    }
    const result = { rangeId: stored.rangeId };
    if (stored.startDate && stored.stopDate) {
        const startDate = DateTime.fromISO(stored.startDate);
        const stopDate = DateTime.fromISO(stored.stopDate);
        // Drop unusable dates but keep the rangeId — the model falls back to
        // its default scale when a custom range arrives without dates.
        if (startDate.isValid && stopDate.isValid && startDate <= stopDate) {
            result.startDate = startDate.startOf("day");
            result.stopDate = stopDate.startOf("day");
        }
    }
    return result;
}
