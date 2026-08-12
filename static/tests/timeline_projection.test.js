import { describe, expect, test } from "@odoo/hoot";

import {
    formatItemPositionStyle,
    getItemPctPosition,
    getItemPositionStyle,
} from "@riverflow/components/timeline/projection";

const { DateTime } = luxon;

describe.current.tags("headless");

const ms = (iso) => DateTime.fromISO(iso).toMillis();

/** A one-year window with a one-month item inside it. */
const WINDOW = {
    itemStartMs: ms("2026-02-01"),
    itemEndMs: ms("2026-03-01"),
    timelineStartMs: ms("2026-01-01"),
    timelineDurationMs: ms("2027-01-01") - ms("2026-01-01"),
    minWidthPct: 0.5,
};

describe("getItemPctPosition", () => {
    test("an item inside the window maps to its share of the timeline", () => {
        const pos = getItemPctPosition(WINDOW);
        expect(Math.round(pos.leftPct * 100) / 100).toBe(8.49);
        expect(Math.round(pos.widthPct * 100) / 100).toBe(7.67);
    });

    test("an item entirely outside the window is hidden", () => {
        expect(
            getItemPctPosition({
                ...WINDOW,
                itemStartMs: ms("2028-01-01"),
                itemEndMs: ms("2028-02-01"),
            })
        ).toBe(null);
    });

    test("an item straddling the start is clamped to the left edge", () => {
        const pos = getItemPctPosition({ ...WINDOW, itemStartMs: ms("2025-06-01") });
        expect(pos.leftPct).toBe(0);
        expect(Math.round(pos.widthPct * 100) / 100).toBe(16.16);
    });

    test("a near-zero-width item still gets minWidthPct so it stays clickable", () => {
        const pos = getItemPctPosition({
            ...WINDOW,
            itemEndMs: WINDOW.itemStartMs + 1000,
        });
        expect(pos.widthPct).toBe(0.5);
    });

    test("a zero-duration timeline has nowhere to place anything", () => {
        expect(getItemPctPosition({ ...WINDOW, timelineDurationMs: 0 })).toBe(null);
    });
});

describe("formatItemPositionStyle", () => {
    const geometry = { trackIndex: 2, trackHeight: 21, trackGap: 1, topOffset: 3 };

    test("track index and top offset compose into the top pixel", () => {
        // 3 + 2 * (21 + 1)
        const style = formatItemPositionStyle({ leftPct: 10, widthPct: 20 }, geometry);
        expect(style).toBe("left: 10%; width: 20%; top: 47px; height: 21px;");
    });

    test("a null position renders hidden", () => {
        expect(formatItemPositionStyle(null, geometry)).toBe("display: none;");
    });

    test("getItemPositionStyle is the formatter composed with the projection", () => {
        // The split exists so a view can post-process the percentages (the
        // credential timeline insets bar edges) and still share the formatter.
        // This pins that the composed helper did not drift.
        const opts = { ...WINDOW, ...geometry };
        expect(getItemPositionStyle(opts)).toBe(
            formatItemPositionStyle(getItemPctPosition(opts), geometry)
        );
    });
});
