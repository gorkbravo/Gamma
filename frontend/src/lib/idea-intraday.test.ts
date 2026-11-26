import { describe, expect, it } from "vitest";
import {
  INTRADAY_QUALITY_LABELS,
  cadenceText,
  formatMark,
  gapDurationText,
  gapPeriodText,
  gapReasonDetail,
  instantTime,
  intradayChartData,
  intradayMetaText,
  intradayQualityTone,
  markFieldText,
  shouldPollIntraday,
  utcClock,
} from "./idea-intraday";
import { INTRADAY_VIEW } from "./idea-intraday.fixture";

describe("idea intraday helpers", () => {
  it("labels qualities and tones anything older than live as a caution", () => {
    expect(INTRADAY_QUALITY_LABELS.delayed_frozen).toBe("Delayed, frozen");
    expect(intradayQualityTone("live")).toBe("accent");
    expect(intradayQualityTone("frozen")).toBe("warning");
    expect(intradayQualityTone(null)).toBe("");
  });

  it("reads naive UTC instants without shifting them to local time", () => {
    expect(utcClock("2026-11-10T15:05:00")).toBe("15:05");
    expect(utcClock(null)).toBe("N/A");
    expect(instantTime("2026-11-10T15:05:00")).toBe(Date.UTC(2026, 10, 10, 15, 5) / 1000);
  });

  it("describes gaps, including an open-ended one", () => {
    expect(gapPeriodText(INTRADAY_VIEW.gaps[0])).toBe("15:05–15:25");
    expect(gapDurationText(INTRADAY_VIEW.gaps[0])).toBe("20 min");
    const open = { ...INTRADAY_VIEW.gaps[0], end: null };
    expect(gapPeriodText(open)).toBe("since 15:05");
    expect(gapDurationText(open)).toBe("Ongoing");
    expect(gapDurationText({ ...INTRADAY_VIEW.gaps[0], end: "2026-11-10T16:10:00" })).toBe("1 h 5 min");
    expect(gapReasonDetail(INTRADAY_VIEW.gaps[0])).toBeNull();
    expect(gapReasonDetail({ ...INTRADAY_VIEW.gaps[0], kind: "skipped", reason: "IBKR error 354: not subscribed." })).toBe(
      "IBKR error 354: not subscribed."
    );
  });

  it("breaks the chart line at gap points and across gaps between marks", () => {
    const points = intradayChartData(INTRADAY_VIEW);
    expect(points.map((point) => Number.isFinite(point.value))).toEqual([true, false, false, true]);
    expect(points[0].value).toBeCloseTo(1.1);
    // Un hueco entre dos marcas sin otra marca dentro añade un punto vacío en su mitad.
    const withoutGapPoint = {
      ...INTRADAY_VIEW,
      points: [INTRADAY_VIEW.points[0], INTRADAY_VIEW.points[2]],
      gaps: [{ ...INTRADAY_VIEW.gaps[0], start: "2026-11-10T15:00:00" }],
    };
    const broken = intradayChartData(withoutGapPoint);
    expect(broken).toHaveLength(3);
    expect(Number.isFinite(broken[1].value)).toBe(false);
    expect(broken.map((point) => point.time)).toEqual([...broken.map((point) => point.time)].sort((a, b) => a - b));
    expect(intradayChartData({ ...INTRADAY_VIEW, points: [INTRADAY_VIEW.points[1]] })).toEqual([]);
    expect(intradayChartData(null)).toEqual([]);
  });

  it("summarises the strip and polls only while it records today", () => {
    expect(intradayMetaText(INTRADAY_VIEW)).toBe("as of 15:25 UTC · 3 marks · 1 gap");
    expect(cadenceText(INTRADAY_VIEW)).toBe("Every 5 min while a leg's market is open, every hour while all are closed");
    expect(shouldPollIntraday(INTRADAY_VIEW)).toBe(true);
    expect(shouldPollIntraday({ ...INTRADAY_VIEW, status: "idle" })).toBe(false);
    // TWS desconectado en la sesión de hoy: se sigue releyendo para ver el hueco y la reconexión.
    const sessionDay = new Date(`${INTRADAY_VIEW.session}T16:00:00Z`);
    const disconnected = { ...INTRADAY_VIEW, status: "idle" as const, tws_connected: false };
    expect(shouldPollIntraday(disconnected, sessionDay)).toBe(true);
    expect(shouldPollIntraday(disconnected, new Date(`2026-11-11T16:00:00Z`))).toBe(false);
    expect(shouldPollIntraday({ ...disconnected, tws_connected: true }, sessionDay)).toBe(false);
    expect(markFieldText("close")).toBe("Prior close");
    expect(markFieldText("delayedLast")).toBe("Last");
    expect(formatMark(1234.5)).toBe("1,234.50");
    expect(formatMark(0.12345)).toBe("0.1235");
    expect(formatMark(null)).toBe("N/A");
  });
});

