import { describe, expect, test } from "@odoo/hoot";

import {
    calculateAverageRowHeight,
    calculateCumulativeHeights,
    stackedTracksHeight,
    statusTrackRowHeight,
} from "@riverflow/components/timeline/row_heights";

describe.current.tags("headless");

/** Credential planning geometry (rivercreds_plan_timeline_renderer.js). */
const CRED = { trackHeight: 21, trackGap: 1, trackPadding: 7 };

/** Crew planning geometry (plan_timeline_track.js). */
const CREW = {
    statusTrackHeight: 22,
    trackHeight: 20,
    trackGap: 1,
    verticalPadding: 12,
    borderHeight: 1,
    sectionHeaderHeight: 20,
};

describe("stackedTracksHeight", () => {
    test("a single-track credential row is 28px", () => {
        // 28 is the contract with --cred-row-height in
        // rivercreds_plan_timeline.scss: the JS must agree with the CSS
        // default, or single-track rows jump on first render.
        expect(stackedTracksHeight(1, CRED)).toBe(28);
    });

    test("extra tracks add their height plus a gap", () => {
        expect(stackedTracksHeight(2, CRED)).toBe(50);
        expect(stackedTracksHeight(3, CRED)).toBe(72);
    });

    test("a zero track count is treated as one", () => {
        expect(stackedTracksHeight(0, CRED)).toBe(28);
    });
});

describe("statusTrackRowHeight", () => {
    test("status track plus stacked item tracks", () => {
        expect(statusTrackRowHeight(1, CREW)).toBe(55);
        expect(statusTrackRowHeight(2, CREW)).toBe(76);
        expect(statusTrackRowHeight(3, CREW)).toBe(97);
    });

    test("a zero track count does not subtract a gap", () => {
        // Callers floor at 1 so this is unreachable today; without the guard
        // it silently returns one pixel short.
        expect(statusTrackRowHeight(0, CREW)).toBe(35);
    });
});

describe("calculateCumulativeHeights", () => {
    const rows = [
        { type: "ship" },
        { type: "ship" },
        { type: "crew" },
        { type: "crew" },
    ];
    const getTrackCount = (row) => (row.type === "ship" ? 1 : 2);

    test("a section header is added on the first row and on every type change", () => {
        const heights = calculateCumulativeHeights(rows, getTrackCount, CREW);
        // 20 + 55 | +55 | +20 + 76 | +76
        expect(heights).toEqual([75, 130, 226, 302]);
    });

    test("heights are strictly increasing", () => {
        const heights = calculateCumulativeHeights(rows, getTrackCount, CREW);
        for (let i = 1; i < heights.length; i++) {
            expect(heights[i] > heights[i - 1]).toBe(true);
        }
    });

    test("no rows means no heights", () => {
        expect(calculateCumulativeHeights([], getTrackCount, CREW)).toEqual([]);
    });
});

describe("calculateAverageRowHeight", () => {
    const rows = [{ type: "ship" }, { type: "crew" }];
    const getTrackCount = (row) => (row.type === "ship" ? 1 : 2);

    test("section headers are excluded, unlike the cumulative heights", () => {
        // (55 + 76) / 2 — the two section headers the cumulative variant adds
        // must not inflate the per-row estimate for unloaded rows.
        expect(calculateAverageRowHeight(rows, getTrackCount, CREW)).toBe(65.5);
    });

    test("no rows means zero", () => {
        expect(calculateAverageRowHeight([], getTrackCount, CREW)).toBe(0);
    });
});
