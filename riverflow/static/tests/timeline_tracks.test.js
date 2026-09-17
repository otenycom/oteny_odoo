import { describe, expect, test } from "@odoo/hoot";

import {
    assignVerticalTracks,
    calculateTrackCount,
} from "@riverflow/components/timeline/tracks";

const { DateTime } = luxon;

describe.current.tags("headless");

const parseDate = (iso) => DateTime.fromISO(iso);
const item = (start, end) => ({ start_date: start, end_date: end });

describe("assignVerticalTracks", () => {
    test("overlapping items stack, and a freed track is reused", () => {
        // A ends exactly when C starts, so C shares A's track rather than
        // opening a third — touching intervals are not an overlap.
        const items = [
            item("2026-01-01", "2026-03-01"),
            item("2026-02-01", "2026-04-01"),
            item("2026-03-01", "2026-05-01"),
        ];
        assignVerticalTracks(items, { parseDate });
        expect(items.map((i) => i.trackIndex)).toEqual([0, 1, 0]);
    });

    test("an item without a start date stays on track 0", () => {
        const items = [{ end_date: "2026-03-01" }, item("2026-01-01", "2026-02-01")];
        assignVerticalTracks(items, { parseDate });
        expect(items[0].trackIndex).toBe(0);
    });

    test("without defaultEnd an open-ended item does not claim a track", () => {
        // Credential planning behaviour: an item with no end date cannot say
        // how long it occupies a track, so it is parked on track 0.
        const items = [{ start_date: "2026-01-01" }, { start_date: "2026-02-01" }];
        assignVerticalTracks(items, { parseDate });
        expect(items.map((i) => i.trackIndex)).toEqual([0, 0]);
    });

    test("with defaultEnd an open-ended item occupies its track", () => {
        // Crew planning behaviour: an ongoing placement blocks the track.
        const items = [{ start_date: "2026-01-01" }, { start_date: "2026-02-01" }];
        assignVerticalTracks(items, {
            parseDate,
            defaultEnd: (start) => start.plus({ year: 2 }),
        });
        expect(items.map((i) => i.trackIndex)).toEqual([0, 1]);
    });

    test("tracks ending before viewStart are reclaimed instead of stacking", () => {
        const items = [
            item("2025-01-01", "2025-02-01"), // entirely before the view
            item("2026-06-01", "2026-07-01"),
        ];
        assignVerticalTracks(items, { parseDate, viewStart: parseDate("2026-01-01") });
        expect(items.map((i) => i.trackIndex)).toEqual([0, 0]);
    });
});

describe("calculateTrackCount", () => {
    test("no items still means one track", () => {
        expect(calculateTrackCount([], { parseDate })).toBe(1);
    });

    test("the count is the highest track index plus one", () => {
        const items = [
            item("2026-01-01", "2026-03-01"),
            item("2026-02-01", "2026-04-01"),
            item("2026-03-01", "2026-05-01"),
        ];
        assignVerticalTracks(items, { parseDate });
        expect(calculateTrackCount(items, { parseDate })).toBe(2);
    });

    test("items entirely before viewStart do not inflate the row", () => {
        const items = [
            item("2025-01-01", "2025-02-01"),
            item("2025-01-15", "2025-02-15"),
        ];
        assignVerticalTracks(items, { parseDate });
        expect(calculateTrackCount(items, { parseDate, viewStart: parseDate("2026-01-01") })).toBe(1);
    });
});
