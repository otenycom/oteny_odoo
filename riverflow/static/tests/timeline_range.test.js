import { describe, expect, test } from "@odoo/hoot";

import {
    calculateColumns,
    computeSnappedGeometry,
    getRangeWindow,
    snapWindowToColumns,
} from "@riverflow/components/timeline/range";

const { DateTime } = luxon;

describe.current.tags("headless");

describe("snapWindowToColumns", () => {
    test("week snapping starts on ISO Monday and covers the window", () => {
        // Window anchored on the 1st of a month — the 1st is a Monday in
        // only ~1/7 of months, so unsnapped week columns drift off ISO weeks.
        for (const iso of ["2026-08-04", "2026-02-15", "2025-12-31", "2026-06-01"]) {
            const focus = DateTime.fromISO(iso);
            const { startDate, stopDate } = getRangeWindow(focus, {
                startMonthOffset: 0,
                duration: { months: 6 },
            });
            const { colStartDate, colStopDate } = snapWindowToColumns(startDate, stopDate, "week");
            expect(colStartDate.weekday).toBe(1, {
                message: `snapped start for ${iso} is an ISO Monday`,
            });
            expect(colStartDate <= startDate).toBe(true);
            expect(colStopDate >= stopDate).toBe(true);
        }
    });

    test("month snapping is a no-op for month-aligned windows", () => {
        const { startDate, stopDate } = getRangeWindow(DateTime.fromISO("2026-08-04"), {
            startMonthOffset: -1,
            duration: { years: 2 },
        });
        const { colStartDate, colStopDate } = snapWindowToColumns(startDate, stopDate, "month");
        expect(colStartDate.toISODate()).toBe(startDate.toISODate());
        // stopDate is the last day of a month; endOf("month") keeps that day
        expect(colStopDate.toISODate()).toBe(stopDate.toISODate());
    });

    test("day snapping keeps the exact dates", () => {
        const startDate = DateTime.fromISO("2026-08-04");
        const stopDate = DateTime.fromISO("2026-09-17");
        const { colStartDate, colStopDate } = snapWindowToColumns(startDate, stopDate, "day");
        expect(colStartDate.toISODate()).toBe("2026-08-04");
        expect(colStopDate.toISODate()).toBe("2026-09-17");
    });
});

describe("computeSnappedGeometry", () => {
    test("week columns are all exactly one ISO week", () => {
        const startDate = DateTime.fromISO("2026-08-01"); // a Saturday
        const stopDate = DateTime.fromISO("2027-01-31");
        const { columns, timelineStart, timelineEnd, timelineDurationMs } =
            computeSnappedGeometry(startDate, stopDate, "week");

        expect(columns.length).toBeGreaterThan(0);
        for (const column of columns) {
            expect(column.start.weekday).toBe(1, {
                message: `column ${column.index} starts on Monday`,
            });
            // One full ISO week: Monday 00:00 through Sunday 23:59:59.999
            expect(column.end.diff(column.start, "days").days).toBeCloseTo(7, { digits: 3 });
        }
        // First/last columns enclose the requested window
        expect(columns[0].start <= startDate).toBe(true);
        expect(columns[columns.length - 1].end >= stopDate).toBe(true);
        // Timeline boundaries match the snapped columns, not the user dates
        expect(timelineStart.toMillis()).toBe(columns[0].start.toMillis());
        expect(timelineDurationMs).toBe(timelineEnd.toMillis() - timelineStart.toMillis());
    });

    test("month geometry over a month-aligned window is unchanged vs raw columns", () => {
        const startDate = DateTime.fromISO("2026-07-01");
        const stopDate = DateTime.fromISO("2028-06-30");
        const { columns } = computeSnappedGeometry(startDate, stopDate, "month");
        const rawColumns = calculateColumns(startDate, stopDate, "month");
        expect(columns.length).toBe(rawColumns.length);
        expect(columns[0].start.toISODate()).toBe(rawColumns[0].start.toISODate());
    });
});
