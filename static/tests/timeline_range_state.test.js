import { describe, expect, test } from "@odoo/hoot";

import {
    recenterRangeWindow,
    resolveCustomRange,
    stepRangeWindow,
} from "@riverflow/components/timeline/range_state";
import { getRangeWindow } from "@riverflow/components/timeline/range";

const { DateTime } = luxon;

describe.current.tags("headless");

const d = (iso) => DateTime.fromISO(iso);

/** Crew planning's scale map, as the model supplies it. */
const crewRange = (rangeId, date) => {
    const window =
        rangeId === "weekly"
            ? { startMonthOffset: -1, duration: { years: 2 } }
            : { startMonthOffset: 0, duration: { months: 6 } };
    const { startDate, stopDate } = getRangeWindow(date, window);
    return { focusDate: date, startDate, stopDate, rangeId };
};

const CUSTOM = {
    rangeId: "custom",
    focusDate: d("2026-08-15"),
    startDate: d("2026-08-01"),
    stopDate: d("2026-08-31"), // 31-day inclusive span
};

describe("stepRangeWindow", () => {
    test("a custom range tiles: the next window starts the day after this one ends", () => {
        // The +1 is the whole point — without it the windows overlap by a day.
        const next = stepRangeWindow(CUSTOM, "next", {
            stepMonths: 6,
            getRangeFromDate: crewRange,
        });
        expect(next.startDate.toISODate()).toBe("2026-09-01");
        expect(next.stopDate.toISODate()).toBe("2026-10-01");
        expect(next.focusDate.toISODate()).toBe("2026-09-15");
        expect(next.startDate.toISODate()).toBe(CUSTOM.stopDate.plus({ day: 1 }).toISODate());
    });

    test("stepping a custom range back and forth returns the original window", () => {
        const next = stepRangeWindow(CUSTOM, "next", {
            stepMonths: 6,
            getRangeFromDate: crewRange,
        });
        const back = stepRangeWindow(
            { ...CUSTOM, ...next },
            "previous",
            { stepMonths: 6, getRangeFromDate: crewRange }
        );
        expect(back.startDate.toISODate()).toBe(CUSTOM.startDate.toISODate());
        expect(back.stopDate.toISODate()).toBe(CUSTOM.stopDate.toISODate());
        expect(back.focusDate.toISODate()).toBe(CUSTOM.focusDate.toISODate());
    });

    test("a scaled range re-derives from a focus date stepped by stepMonths", () => {
        const scaled = {
            rangeId: "weekly",
            focusDate: d("2026-08-15"),
            startDate: d("2026-07-01"),
            stopDate: d("2028-06-30"),
        };
        const seen = [];
        const spy = (rangeId, date) => {
            seen.push([rangeId, date.toISODate()]);
            return crewRange(rangeId, date);
        };

        stepRangeWindow(scaled, "next", { stepMonths: 6, getRangeFromDate: spy });
        stepRangeWindow(scaled, "previous", { stepMonths: 3, getRangeFromDate: spy });

        expect(seen).toEqual([
            ["weekly", "2027-02-15"],
            ["weekly", "2026-05-15"],
        ]);
    });
});

describe("recenterRangeWindow", () => {
    test("a custom range keeps its span, centred on today", () => {
        // No +1 here, unlike a page step: re-centring preserves the window
        // rather than tiling the next one. The asymmetry is intentional.
        const today = d("2026-12-25");
        const out = recenterRangeWindow(CUSTOM, today, { getRangeFromDate: crewRange });

        expect(out.startDate.toISODate()).toBe("2026-12-10");
        expect(out.stopDate.toISODate()).toBe("2027-01-09");
        expect(out.focusDate.toISODate()).toBe("2026-12-25");
        expect(out.stopDate.diff(out.startDate, "day").days).toBe(
            CUSTOM.stopDate.diff(CUSTOM.startDate, "day").days
        );
    });

    test("a single-day custom range collapses onto today", () => {
        const today = d("2026-12-25");
        const single = { ...CUSTOM, startDate: d("2026-08-15"), stopDate: d("2026-08-15") };
        const out = recenterRangeWindow(single, today, { getRangeFromDate: crewRange });

        expect(out.startDate.toISODate()).toBe("2026-12-25");
        expect(out.stopDate.toISODate()).toBe("2026-12-25");
    });

    test("a scaled range is re-derived around today", () => {
        const today = d("2026-12-25");
        const scaled = { rangeId: "weekly", startDate: d("2026-07-01"), stopDate: d("2028-06-30") };
        const out = recenterRangeWindow(scaled, today, { getRangeFromDate: crewRange });

        expect(out.focusDate.toISODate()).toBe("2026-12-25");
        expect(out.startDate.toISODate()).toBe("2026-11-01");
        expect(out.stopDate.toISODate()).toBe("2028-10-31");
    });
});

describe("resolveCustomRange", () => {
    const focusDate = d("2026-08-15");

    test("no usable dates returns null so the caller can fall back", () => {
        expect(resolveCustomRange({ startDate: null, stopDate: null, focusDate })).toBe(null);
    });

    test("a one-sided window is completed to one year", () => {
        const fromStart = resolveCustomRange({
            startDate: d("2026-01-01"),
            stopDate: null,
            focusDate,
        });
        expect(fromStart.stopDate.toISODate()).toBe("2026-12-31");

        const fromStop = resolveCustomRange({
            startDate: null,
            stopDate: d("2026-12-31"),
            focusDate,
        });
        expect(fromStop.startDate.toISODate()).toBe("2025-12-31");
    });

    test("a backwards window returns null", () => {
        expect(
            resolveCustomRange({
                startDate: d("2026-12-31"),
                stopDate: d("2026-01-01"),
                focusDate,
            })
        ).toBe(null);
    });

    test("the focus date is clamped into the window at both ends", () => {
        const window = { startDate: d("2026-06-01"), stopDate: d("2026-07-01") };
        expect(
            resolveCustomRange({ ...window, focusDate: d("2026-01-01") }).focusDate.toISODate()
        ).toBe("2026-06-01");
        expect(
            resolveCustomRange({ ...window, focusDate: d("2026-12-01") }).focusDate.toISODate()
        ).toBe("2026-07-01");
    });

    test("clampWindow narrows the window — crew planning's 10-year span cap", () => {
        const out = resolveCustomRange({
            startDate: d("2020-01-01"),
            stopDate: d("2040-01-01"),
            focusDate,
            clampWindow: (start, stop) => ({
                startDate: start,
                stopDate:
                    start.plus({ year: 10, day: -1 }) < stop
                        ? start.plus({ year: 10, day: -1 })
                        : stop,
            }),
        });
        expect(out.startDate.toISODate()).toBe("2020-01-01");
        expect(out.stopDate.toISODate()).toBe("2029-12-31");
    });

    test("clampWindow narrows both ends — credential planning's data horizon", () => {
        const min = d("2025-01-01");
        const max = d("2028-01-01");
        const out = resolveCustomRange({
            startDate: d("2020-01-01"),
            stopDate: d("2040-01-01"),
            focusDate,
            clampWindow: (start, stop) => ({
                startDate: start < min ? min : start,
                stopDate: stop > max ? max : stop,
            }),
        });
        expect(out.startDate.toISODate()).toBe("2025-01-01");
        expect(out.stopDate.toISODate()).toBe("2028-01-01");
    });

    test("a clamp that inverts the window returns null", () => {
        // The order matters: the emptiness check runs AFTER the clamp, so a
        // horizon that excludes the whole request falls back rather than
        // rendering zero columns.
        expect(
            resolveCustomRange({
                startDate: d("2026-01-01"),
                stopDate: d("2026-12-01"),
                focusDate: d("2026-06-01"),
                clampWindow: () => ({ startDate: d("2027-01-01"), stopDate: d("2026-01-01") }),
            })
        ).toBe(null);
    });
});
