import { describe, expect, test } from "@odoo/hoot";

import {
    layoutFromRange,
    rangeParamsFromLayout,
} from "@riverflow/components/timeline/layout_range";
import { getRangeWindow } from "@riverflow/components/timeline/range";

const { DateTime } = luxon;

describe.current.tags("headless");

const d = (iso) => DateTime.fromISO(iso);
const TODAY = d("2026-09-09");

/** Credential planning's scale map, as its model supplies it. */
const credRange = (rangeId, date) => {
    const window =
        rangeId === "weekly"
            ? { startMonthOffset: 0, duration: { months: 6 } }
            : { startMonthOffset: -1, duration: { years: 2 } };
    const { startDate, stopDate } = getRangeWindow(date, window);
    return { focusDate: date, startDate, stopDate, rangeId };
};

describe("layoutFromRange", () => {
    test("a scale stores only its id — the window is re-derived around today on apply", () => {
        expect(layoutFromRange({ rangeId: "monthly", startDate: d("2026-08-01"), stopDate: d("2028-07-31") }))
            .toEqual({ range_id: "monthly" });
    });

    test("a custom range stores its fixed dates", () => {
        expect(layoutFromRange({ rangeId: "custom", startDate: d("2026-10-01"), stopDate: d("2026-12-31") }))
            .toEqual({ range_id: "custom", start_date: "2026-10-01", stop_date: "2026-12-31" });
    });
});

describe("rangeParamsFromLayout", () => {
    test("a scale applies as its default window around today", () => {
        const out = rangeParamsFromLayout({ range_id: "weekly" }, { today: TODAY, getRangeFromDate: credRange });
        expect(out.rangeId).toBe("weekly");
        expect(out.startDate.toISODate()).toBe("2026-09-01");
        expect(out.stopDate.toISODate()).toBe("2027-02-28");
        expect(out.focusDate.toISODate()).toBe("2026-09-09");
    });

    test("fixed dates apply as a custom range with the focus kept inside it", () => {
        const out = rangeParamsFromLayout(
            { range_id: "custom", start_date: "2026-10-01", stop_date: "2026-12-31" },
            { today: TODAY, getRangeFromDate: credRange }
        );
        expect(out.rangeId).toBe("custom");
        expect(out.startDate.toISODate()).toBe("2026-10-01");
        expect(out.stopDate.toISODate()).toBe("2026-12-31");
        // Today is before the window, so the focus snaps to its start
        expect(out.focusDate.toISODate()).toBe("2026-10-01");
    });

    test("a relative period counts whole months from the start of today's month", () => {
        // "last month through the next five": -1 and 6
        const out = rangeParamsFromLayout(
            { range_id: "custom", relative_period: { start_month_offset: -1, months: 6 } },
            { today: TODAY, getRangeFromDate: credRange }
        );
        expect(out.rangeId).toBe("custom");
        expect(out.startDate.toISODate()).toBe("2026-08-01");
        expect(out.stopDate.toISODate()).toBe("2027-01-31");
        expect(out.focusDate.toISODate()).toBe("2026-09-09");
    });

    test("a relative period wins over stale fixed dates stored beside it", () => {
        const out = rangeParamsFromLayout(
            {
                range_id: "custom",
                start_date: "2020-01-01",
                stop_date: "2020-02-01",
                relative_period: { start_month_offset: 0, months: 3 },
            },
            { today: TODAY, getRangeFromDate: credRange }
        );
        expect(out.startDate.toISODate()).toBe("2026-09-01");
        expect(out.stopDate.toISODate()).toBe("2026-11-30");
    });

    test("the view's horizon clamp is applied to a custom window", () => {
        const clampWindow = (start, stop) => ({
            startDate: start,
            stopDate: stop > d("2026-11-15") ? d("2026-11-15") : stop,
        });
        const out = rangeParamsFromLayout(
            { range_id: "custom", relative_period: { start_month_offset: 0, months: 3 } },
            { today: TODAY, getRangeFromDate: credRange, clampWindow }
        );
        expect(out.stopDate.toISODate()).toBe("2026-11-15");
    });

    test("layouts without a usable period yield null", () => {
        const opts = { today: TODAY, getRangeFromDate: credRange };
        expect(rangeParamsFromLayout(null, opts)).toBe(null);
        expect(rangeParamsFromLayout({ optional_columns: ["x"] }, opts)).toBe(null);
        expect(rangeParamsFromLayout({ range_id: "custom" }, opts)).toBe(null);
        expect(rangeParamsFromLayout({ range_id: "custom", start_date: "nope", stop_date: "2026-01-01" }, opts)).toBe(null);
        expect(rangeParamsFromLayout({ range_id: "custom", relative_period: { months: 0 } }, opts)).toBe(null);
    });
});
