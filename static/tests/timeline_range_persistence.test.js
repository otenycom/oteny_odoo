import { describe, expect, test } from "@odoo/hoot";

import {
    parseStoredRange,
    serializeStoredRange,
} from "@riverflow/components/timeline/range_persistence";

const { DateTime } = luxon;

describe.current.tags("headless");

describe("serializeStoredRange / parseStoredRange", () => {
    test("custom range round-trips with its dates", () => {
        const raw = serializeStoredRange({
            rangeId: "custom",
            startDate: DateTime.fromISO("2026-08-01"),
            stopDate: DateTime.fromISO("2026-12-31"),
        });
        const parsed = parseStoredRange(raw);
        expect(parsed.rangeId).toBe("custom");
        expect(parsed.startDate.toISODate()).toBe("2026-08-01");
        expect(parsed.stopDate.toISODate()).toBe("2026-12-31");
    });

    test("non-custom range stores only the rangeId", () => {
        const raw = serializeStoredRange({
            rangeId: "weekly",
            // Dates present on the metaData but irrelevant for weekly
            startDate: DateTime.fromISO("2026-08-01"),
            stopDate: DateTime.fromISO("2026-12-31"),
        });
        const parsed = parseStoredRange(raw);
        expect(parsed.rangeId).toBe("weekly");
        expect(parsed.startDate).toBe(undefined);
        expect(parsed.stopDate).toBe(undefined);
    });

    test("legacy bare-string values parse as a rangeId without dates", () => {
        // Older versions stored the bare rangeId string via localStorage
        expect(parseStoredRange("weekly").rangeId).toBe("weekly");
        expect(parseStoredRange("monthly").rangeId).toBe("monthly");
        const custom = parseStoredRange("custom");
        expect(custom.rangeId).toBe("custom");
        expect(custom.startDate).toBe(undefined);
    });

    test("garbage and invalid dates degrade cleanly", () => {
        expect(parseStoredRange(null)).toBe(null);
        expect(parseStoredRange("")).toBe(null);
        expect(parseStoredRange("null")).toBe(null);
        expect(parseStoredRange("42")).toBe(null);
        expect(parseStoredRange('{"noRangeId": true}')).toBe(null);

        // Unparseable dates: rangeId survives, dates are dropped
        const badDates = parseStoredRange(
            '{"rangeId":"custom","startDate":"not-a-date","stopDate":"2026-01-01"}'
        );
        expect(badDates.rangeId).toBe("custom");
        expect(badDates.startDate).toBe(undefined);

        // start after stop: dates are dropped
        const inverted = parseStoredRange(
            '{"rangeId":"custom","startDate":"2026-06-01","stopDate":"2026-01-01"}'
        );
        expect(inverted.rangeId).toBe("custom");
        expect(inverted.startDate).toBe(undefined);
    });
});
